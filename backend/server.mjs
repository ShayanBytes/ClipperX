import http from 'node:http';
import { mkdir, readFile, writeFile, readdir, rm, stat } from 'node:fs/promises';
import { createReadStream, createWriteStream, readFileSync } from 'node:fs';
import { spawn, spawnSync } from 'node:child_process';
import path from 'node:path';
import crypto from 'node:crypto';
import { fileURLToPath } from 'node:url';
import { JobQueue } from './job-queue.mjs';
import { runAdvanced } from './advanced-runner.mjs';
import { resolvePython, savePython } from '../scripts/python-resolver.mjs';

const ROOT = path.resolve(path.dirname(fileURLToPath(import.meta.url)), '..');
const DATA = process.env.CLIPPERX_DATA_DIR || path.join(ROOT, 'runtime');
const PROJECTS = path.join(DATA, 'projects');
const PORT = Number(process.env.CLIPPERX_API_PORT || 8787);
const MAX_UPLOAD = Number(process.env.CLIPPERX_MAX_UPLOAD_BYTES || 2 * 1024 ** 3);
const queue = new JobQueue(Number(process.env.CLIPPERX_CONCURRENCY || 1));
await mkdir(PROJECTS, { recursive: true });

const PROVIDERS = [
  { id: 'gemini', name: 'Google Gemini', freeOption: true, models: ['gemini-2.5-flash', 'gemini-2.5-flash-lite'] },
  { id: 'openai', name: 'OpenAI', freeOption: false, models: ['gpt-4.1-mini', 'gpt-4o-mini'] },
  { id: 'anthropic', name: 'Anthropic', freeOption: false, models: ['claude-sonnet-4-20250514'] },
  { id: 'openrouter', name: 'OpenRouter', freeOption: true, models: ['openrouter/free'] },
  { id: 'custom', name: 'Custom OpenAI-compatible', freeOption: false, models: [] },
];

const json = (res, status, body) => {
  const data = Buffer.from(JSON.stringify(body));
  res.writeHead(status, { 'content-type': 'application/json; charset=utf-8', 'content-length': data.length, 'cache-control': 'no-store', 'access-control-allow-origin':'*' });
  res.end(data);
};
const readJson = async (req) => {
  const chunks = []; let size = 0;
  for await (const chunk of req) { size += chunk.length; if (size > 1024 * 1024) throw new Error('JSON body too large'); chunks.push(chunk); }
  return chunks.length ? JSON.parse(Buffer.concat(chunks).toString('utf8')) : {};
};
const safeName = (value = 'video.mp4') => path.basename(value).replace(/[^a-zA-Z0-9._-]/g, '_').slice(0, 120) || 'video.mp4';
const projectDir = (id) => path.join(PROJECTS, id.replace(/[^a-zA-Z0-9_-]/g, ''));
const metadataPath = (id) => path.join(projectDir(id), 'project.json');
const loadProject = async (id) => JSON.parse(await readFile(metadataPath(id), 'utf8'));
const saveProject = async (project) => { project.updatedAt = new Date().toISOString(); await writeFile(metadataPath(project.id), JSON.stringify(project, null, 2)); return project; };
const patchProject = async (id, patch) => saveProject({ ...(await loadProject(id)), ...patch });
const commandExists = (name) => spawnSync(name, ['-version'], { stdio: 'ignore' }).status === 0;
let pythonInfo=resolvePython({requirePip:false,minMinor:10,maxMinor:12})||resolvePython({requirePip:false});let PYTHON=pythonInfo?.executable||process.env.CLIPPERX_PYTHON||(process.platform==='win32'?'python':'python3');process.env.CLIPPERX_PYTHON=PYTHON;const activatePython=(info)=>{if(!info)return false;pythonInfo=info;PYTHON=info.executable;process.env.CLIPPERX_PYTHON=PYTHON;savePython(info);return true;};
const PY_MODULES=[['cv2','opencv-python','OpenCV video processing'],['numpy','numpy','Numerical arrays'],['ultralytics','ultralytics','YOLO object detection'],['faster_whisper','faster-whisper','Speech transcription'],['scenedetect','scenedetect[opencv]','Scene detection'],['mediapipe','mediapipe','Face detection'],['scipy','scipy','Signal processing'],['soundfile','soundfile','Audio decoding'],['requests','requests','Stage 1 API transport']];
let repairState={status:'idle',message:'No repair has run yet.'};
function diagnoseEngine(){const script=`import importlib.util,json;mods=${JSON.stringify(PY_MODULES.map(x=>x[0]))};print(json.dumps({m:bool(importlib.util.find_spec(m)) for m in mods}))`;const check=spawnSync(PYTHON,['-c',script],{encoding:'utf8',windowsHide:true,timeout:15000});let found={};try{found=JSON.parse(check.stdout||'{}');}catch{}const python=check.status===0;const missing=PY_MODULES.filter(([module])=>!found[module]).map(([module,packageName,label])=>({module,package:packageName,label}));const ffmpeg=commandExists('ffmpeg'),ffprobe=commandExists('ffprobe');const issues=[];if(!python)issues.push('Python is missing or cannot be started.');if(!ffmpeg||!ffprobe)issues.push('FFmpeg or FFprobe is missing from PATH.');if(missing.length)issues.push(`${missing.length} Python engine package${missing.length===1?' is':'s are'} missing.`);return {ready:python&&ffmpeg&&ffprobe&&!missing.length,python,ffmpeg,ffprobe,missing,issues,repair:repairState,command:`${PYTHON} -m pip install --user -r requirements.txt`};}
function classifyEngineError(value){const message=String(value||'Unknown engine error');const moduleMatch=message.match(/No module named ['\"]([^'\"]+)/i);if(moduleMatch){const module=moduleMatch[1],known=PY_MODULES.find(item=>item[0]===module);return {code:'PYTHON_MODULE_MISSING',title:`${known?.[2]||module} is not installed`,summary:`ClipperX could not start the advanced engine because the Python module “${module}” is missing.`,steps:['Click Repair engine below.','Wait for package installation to finish.','Run the project again.'],command:`${PYTHON} -m pip install --user ${known?.[1]||module}`,canRepair:true};}if(/ffmpeg|ffprobe/i.test(message)&&/not found|enoent|missing/i.test(message))return {code:'FFMPEG_MISSING',title:'FFmpeg is not available',summary:'ClipperX needs FFmpeg and FFprobe to read and render video.',steps:['Install FFmpeg for Windows.','Add its bin folder to PATH.','Restart ClipperX and run Diagnostics.'],command:'ffmpeg -version',canRepair:false};if(/no space|disk full|enospc/i.test(message))return {code:'DISK_FULL',title:'Not enough free disk space',summary:'Video analysis and rendering need temporary space for proxies and frame output.',steps:['Free at least twice the source video size.','Clear old projects you no longer need.','Run the project again.'],canRepair:false};if(/memory|bad allocation|out of memory/i.test(message))return {code:'OUT_OF_MEMORY',title:'The computer ran out of memory',summary:'This video or model is too heavy for the currently available RAM.',steps:['Close other heavy apps.','Try a shorter or lower-resolution video.','Use the smallest YOLO and Whisper models.'],canRepair:false};if(/permission|eacces|access is denied/i.test(message))return {code:'PERMISSION_DENIED',title:'ClipperX cannot write a required file',summary:'Windows blocked access to the project or temporary folder.',steps:['Move the project to a normal user folder.','Avoid protected folders such as Program Files.','Restart ClipperX normally, not as another user.'],canRepair:false};if(/download|network|connection|timed out/i.test(message))return {code:'MODEL_DOWNLOAD',title:'A model could not be downloaded',summary:'The first run needs internet access to download local YOLO or Whisper model files.',steps:['Check the internet connection.','Disable VPN or proxy restrictions temporarily.','Run the project again; completed downloads are cached.'],canRepair:false};return {code:'ENGINE_FAILURE',title:'Advanced processing stopped',summary:'The engine stopped at the current checkpoint. Your source video and completed analysis files are safe.',steps:['Open Run Details to see the last completed checkpoint.','Run Diagnostics to check local dependencies.','Try a short 720p test clip to isolate the problem.'],canRepair:true};}
function startEngineRepair(){if(repairState.status==='running')return repairState;const candidate=resolvePython({ensurePip:true,requirePip:true,useConfig:true,minMinor:10,maxMinor:12});if(!candidate){repairState={status:'failed',message:'No compatible Python was found. Install 64-bit Python 3.11 or 3.12 with pip, restart ClipperX, then click Repair engine again.',log:'ClipperX requires Python 3.10–3.12 because MediaPipe and the video stack may not support newer Python releases.'};return repairState;}activatePython(candidate);repairState={status:'running',message:`Installing engine packages into Python ${candidate.version}…`,startedAt:new Date().toISOString(),python:candidate.executable};const userArgs=candidate.venv?[]:['--user'];const child=spawn(PYTHON,['-m','pip','install','--disable-pip-version-check',...userArgs,'-r',path.join(ROOT,'requirements.txt')],{cwd:ROOT,windowsHide:true,stdio:['ignore','pipe','pipe']});let log='';for(const stream of [child.stdout,child.stderr])stream.on('data',chunk=>{log=(log+chunk.toString()).slice(-12000);repairState={...repairState,log};});child.on('error',error=>{repairState={status:'failed',message:error.message,log};});child.on('close',code=>{const finalInfo=resolvePython({requirePip:true,useConfig:true,minMinor:10,maxMinor:12});if(code===0&&finalInfo)activatePython(finalInfo);const tail=log.trim().split(/\r?\n/).slice(-6).join(' ');repairState={status:code===0?'complete':'failed',message:code===0?'Engine packages installed. Diagnostics will verify them automatically.':`Package installation failed.${tail?' '+tail:''}`,log,finishedAt:new Date().toISOString()};});return repairState;}

function run(command, args, cwd) {
  return new Promise((resolve, reject) => {
    const child = spawn(command, args, { cwd, windowsHide: true });
    let stderr = '';
    child.stderr.on('data', (chunk) => { stderr += chunk.toString(); if (stderr.length > 16000) stderr = stderr.slice(-16000); });
    child.on('error', reject);
    child.on('close', (code) => code === 0 ? resolve(stderr) : reject(new Error(`${command} exited ${code}: ${stderr.slice(-3000)}`)));
  });
}

async function probeVideo(input) {
  const result = await new Promise((resolve, reject) => {
    const child = spawn('ffprobe', ['-v','error','-show_entries','format=duration,size:stream=index,codec_type,codec_name,width,height,r_frame_rate','-of','json', input]);
    const out = []; const err = [];
    child.stdout.on('data', (c) => out.push(c)); child.stderr.on('data', (c) => err.push(c));
    child.on('error', reject); child.on('close', (code) => code === 0 ? resolve(Buffer.concat(out).toString()) : reject(new Error(Buffer.concat(err).toString())));
  });
  return JSON.parse(result);
}

async function callVision({ provider, model, apiKey, baseUrl, imageBase64, profile, freeOnly }) {
  if (freeOnly && !['gemini', 'openrouter'].includes(provider)) throw new Error('Free-only mode blocks this paid provider. Disable it explicitly to continue.');
  const prompt = `You are ClipperX's conservative shot planner. Inspect this 8-frame contact sheet. Content profile: ${profile}. Return JSON only with keys compositionMode (single|pair|group|action|wide|blurred_background), confidence (0..1), primaryEntities (array), requiredEntities (array), reason (short string). Prefer wide or blurred_background if uncertain.`;
  const timeout = AbortSignal.timeout(25000);
  let response;
  if (provider === 'gemini') {
    const geminiUrl = ['https:', '', 'generativelanguage.googleapis.com', 'v1beta', 'models', encodeURIComponent(model) + ':generateContent'].join('/') + '?key=' + encodeURIComponent(apiKey);
    response = await fetch(geminiUrl, { method:'POST', signal: timeout, headers:{'content-type':'application/json'}, body: JSON.stringify({ contents:[{ parts:[{text:prompt},{inline_data:{mime_type:'image/jpeg',data:imageBase64}}] }], generationConfig:{ responseMimeType:'application/json', temperature:0.1 } }) });
    const data = await response.json(); if (!response.ok) throw new Error(data?.error?.message || 'Gemini request failed');
    return parseModelJson(data?.candidates?.[0]?.content?.parts?.[0]?.text);
  }
  if (provider === 'anthropic') {
    response = await fetch('https://api.anthropic.com/v1/messages', { method:'POST', signal: timeout, headers:{'content-type':'application/json','x-api-key':apiKey,'anthropic-version':'2023-06-01'}, body: JSON.stringify({ model, max_tokens:500, temperature:0, messages:[{role:'user',content:[{type:'image',source:{type:'base64',media_type:'image/jpeg',data:imageBase64}},{type:'text',text:prompt}]}] }) });
    const data = await response.json(); if (!response.ok) throw new Error(data?.error?.message || 'Anthropic request failed');
    return parseModelJson(data?.content?.find((x) => x.type === 'text')?.text);
  }
  const endpoint = provider === 'openrouter' ? 'https://openrouter.ai/api/v1' : provider === 'custom' ? String(baseUrl || '').replace(/\/$/, '') : 'https://api.openai.com/v1';
  if (!endpoint) throw new Error('Custom base URL is required');
  response = await fetch(`${endpoint}/chat/completions`, { method:'POST', signal: timeout, headers:{'content-type':'application/json','authorization':`Bearer ${apiKey}`,'HTTP-Referer':'http://localhost:4173','X-Title':'ClipperX'}, body: JSON.stringify({ model, temperature:0.1, max_tokens:500, response_format:{type:'json_object'}, messages:[{role:'user',content:[{type:'text',text:prompt},{type:'image_url',image_url:{url:`data:image/jpeg;base64,${imageBase64}`}}]}] }) });
  const data = await response.json(); if (!response.ok) throw new Error(data?.error?.message || 'Vision request failed');
  return parseModelJson(data?.choices?.[0]?.message?.content);
}

function parseModelJson(text = '') {
  const cleaned = String(text).replace(/^```(?:json)?/i,'').replace(/```$/,'').trim();
  const start = cleaned.indexOf('{'), end = cleaned.lastIndexOf('}');
  if (start < 0 || end < 0) throw new Error('Model did not return JSON');
  const plan = JSON.parse(cleaned.slice(start, end + 1));
  const allowed = new Set(['single','pair','group','action','wide','blurred_background']);
  if (!allowed.has(plan.compositionMode)) plan.compositionMode = 'wide';
  plan.confidence = Math.max(0, Math.min(1, Number(plan.confidence) || 0));
  return plan;
}

function parseCapabilityJson(text='') {
  const clean=String(text).replace(/^```(?:json)?/i,'').replace(/```$/,'').trim();
  const start=clean.indexOf('{'),end=clean.lastIndexOf('}');
  if(start<0||end<start)throw new Error('Model returned no JSON object');
  return JSON.parse(clean.slice(start,end+1));
}

async function testCustomStoryCapability({apiKey,baseUrl,model}) {
  const root=String(baseUrl||'').replace(/\/$/,'');
  if(!root)throw new Error('Custom base URL is required');
  if(!model)throw new Error('Model ID is required');
  const demo={duration:6,transcript:'Alex says start. The performer completes the attempt. Sam reacts.',tracks:[{trackId:'person-demo-speaker',visibility:1,meanCenter:[0.28,0.52],activeSpeakerVotes:8},{trackId:'person-demo-performer',visibility:1,meanCenter:[0.67,0.55],meanSpeed:0.18}],pairwise:{coVisibleRate:1,meanCenterDistance:0.39,singleVerticalCropLikely:false}};
  const prompt=`ClipperX automatic-mode capability test. Use only this demo evidence: ${JSON.stringify(demo)}. Return JSON only with exactly: {"globalSummary":"string","events":[{"id":"e0","start":0,"end":1,"mustShowTrackIds":["existing demo track"],"summary":"string"}],"directingHints":[{"eventId":"e0","primaryTrackIds":["existing demo track"],"spatialIntent":"single_subject|shared_region|two_independent_regions|continuous_action","coordinateReason":"string citing coordinates"}]}. Never invent a track ID.`;
  const headers={'content-type':'application/json',authorization:`Bearer ${apiKey}`,'HTTP-Referer':'http://localhost:5173','X-Title':'ClipperX capability test'};
  const started=Date.now();
  const send=(withFormat)=>fetch(`${root}/chat/completions`,{method:'POST',signal:AbortSignal.timeout(30000),headers,body:JSON.stringify({model,temperature:0,max_tokens:900,...(withFormat?{response_format:{type:'json_object'}}:{}),messages:[{role:'user',content:prompt}]})});
  let response=await send(true);
  if(!response.ok&&[400,404,422].includes(response.status))response=await send(false);
  const data=await response.json().catch(()=>({}));
  if(!response.ok)throw new Error(data?.error?.message||`Custom endpoint returned HTTP ${response.status}`);
  try {
    const value=parseCapabilityJson(data?.choices?.[0]?.message?.content);
    const tracks=new Set(['person-demo-speaker','person-demo-performer']);
    const events=Array.isArray(value.events)?value.events:[],hints=Array.isArray(value.directingHints)?value.directingHints:[];
    const ids=new Set(events.map(row=>String(row.id)));
    const referenced=[...events.flatMap(row=>row.mustShowTrackIds||[]),...hints.flatMap(row=>row.primaryTrackIds||[])];
    const grounded=referenced.length>0&&referenced.every(track=>tracks.has(String(track)));
    const schema=typeof value.globalSummary==='string'&&events.length>0&&hints.length>0&&hints.every(row=>ids.has(String(row.eventId)));
    const passed=schema&&grounded;
    return {passed,modeRecommendation:passed?'automatic':'semi-automated',latencyMs:Date.now()-started,checks:{chatCompletion:true,validJson:true,storySchema:schema,groundedTrackIds:grounded},message:passed?'Demo story test passed. Automatic mode is supported.':'The endpoint answered, but its JSON was not grounded enough. Use semi-automated mode.'};
  } catch(error) {
    return {passed:false,modeRecommendation:'semi-automated',latencyMs:Date.now()-started,checks:{chatCompletion:true,validJson:false,storySchema:false,groundedTrackIds:false},message:`The endpoint connected but failed the demo JSON test: ${error.message}`};
  }
}

async function validateProvider(body) {
  const {provider,apiKey,baseUrl,model}=body;
  if(!apiKey)throw new Error('API key is required');
  if(provider==='custom')return {ok:true,provider,model,capabilityTest:await testCustomStoryCapability({apiKey,baseUrl,model})};
  const signal=AbortSignal.timeout(12000);let url;let headers={};
  if(provider==='gemini')url=['https:','','generativelanguage.googleapis.com','v1beta','models'].join('/')+'?key='+encodeURIComponent(apiKey);
  else if(provider==='anthropic'){url=['https:','','api.anthropic.com','v1','models'].join('/')+'?limit=5';headers={'x-api-key':apiKey,'anthropic-version':'2023-06-01'};}
  else{const root=provider==='openrouter'?['https:','','openrouter.ai','api','v1'].join('/'):['https:','','api.openai.com','v1'].join('/');url=`${root}/models`;headers={authorization:`Bearer ${apiKey}`};}
  const response=await fetch(url,{headers,signal});const data=await response.json().catch(()=>({}));
  if(!response.ok)throw new Error(data?.error?.message||`Provider returned HTTP ${response.status}`);
  return {ok:true,provider,modelCount:Array.isArray(data?.data)?data.data.length:Array.isArray(data?.models)?data.models.length:null,capabilityTest:{passed:true,modeRecommendation:'automatic',checks:{connection:true},message:'Connection verified. Automatic mode is available.'}};
}

async function runPipeline(id, credentials = {}) {
  const dir = projectDir(id);
  try {
    let project = await patchProject(id, { status:'Processing', progress:8, error:null, stage:'Probing video' });
    const input = path.join(dir, project.inputFile);
    const probe = await probeVideo(input);
    const video = probe.streams?.find((s) => s.codec_type === 'video');
    const duration = Number(probe.format?.duration || 0);
    project = await patchProject(id, { progress:18, stage:'Creating lightweight proxy', media:{ duration, width:video?.width, height:video?.height, codec:video?.codec_name, size:Number(probe.format?.size || 0) } });
    await run('ffmpeg', ['-y','-i',input,'-vf','scale=-2:480','-r','15','-c:v','libx264','-preset','veryfast','-crf','28','-an',path.join(dir,'proxy.mp4')], dir);
    await patchProject(id, { progress:42, stage:'Sampling story frames' });
    const interval = Math.max(0.05, duration / 8 || 1);
    await run('ffmpeg', ['-y','-i',input,'-vf',`fps=1/${interval},scale=320:-2,tile=4x2:padding=4:margin=4:color=0x292823`,'-frames:v','1',path.join(dir,'contact.jpg')], dir);
    await run('ffmpeg', ['-y','-ss',String(Math.min(1, Math.max(0,duration/4))),'-i',input,'-frames:v','1','-vf','scale=640:-2',path.join(dir,'thumbnail.jpg')], dir);
    await patchProject(id, { progress:58, stage:'Planning the composition' });
    let plan = { compositionMode: project.profile === 'Single' ? 'single' : 'blurred_background', confidence:0.55, primaryEntities:[], requiredEntities:[], reason:'Safe local fallback; connect a vision model for semantic planning.', source:'local-fallback' };
    if (credentials.apiKey && credentials.provider && credentials.model) {
      try { const imageBase64 = (await readFile(path.join(dir,'contact.jpg'))).toString('base64'); plan = { ...(await callVision({ ...credentials, imageBase64, profile:project.profile })), source:credentials.provider }; }
      catch (error) { plan.modelError = error.message; }
    }
    await writeFile(path.join(dir,'plan.json'), JSON.stringify(plan, null, 2));
    await patchProject(id, { progress:72, stage:'Rendering safe vertical preview', plan });
    const filter = plan.compositionMode === 'single'
      ? '[0:v]scale=1080:1920:force_original_aspect_ratio=increase,crop=1080:1920[v]'
      : '[0:v]scale=1080:1920:force_original_aspect_ratio=increase,crop=1080:1920,boxblur=28:2[bg];[0:v]scale=1080:1920:force_original_aspect_ratio=decrease[fg];[bg][fg]overlay=(W-w)/2:(H-h)/2[v]';
    await run('ffmpeg', ['-y','-i',input,'-filter_complex',filter,'-map','[v]','-map','0:a?','-t',String(Math.min(duration || 30,30)),'-c:v','libx264','-preset','veryfast','-crf','24','-c:a','aac','-movflags','+faststart',path.join(dir,'preview.mp4')], dir);
    await patchProject(id, { status:'Ready', progress:100, stage:'Preview ready', outputs:{ proxy:'/api/projects/'+id+'/assets/proxy.mp4', preview:'/api/projects/'+id+'/assets/preview.mp4', thumbnail:'/api/projects/'+id+'/assets/thumbnail.jpg', contact:'/api/projects/'+id+'/assets/contact.jpg', plan:'/api/projects/'+id+'/assets/plan.json' } });
  } catch (error) {
    await patchProject(id, { status:'Failed', stage:'Failed', error:error.message, progress:0 }).catch(() => {});
  }
}

async function runAdvancedJob(id, credentials = {}) {
  const dir = projectDir(id); const project = await loadProject(id); const input = path.join(dir, project.inputFile);
  const corrections = path.join(dir, 'corrections.json');
  try { await stat(corrections); } catch { await writeFile(corrections, '[]'); }
  await patchProject(id,{status:'Processing',progress:1,stage:'Queued advanced engine',error:null});
  queue.enqueue(id, async ({signal}) => {
    try {
      await runAdvanced({root:ROOT,projectDir:dir,input,profile:project.profile,corrections,semantic:path.join(dir,'semantic.json'),signal,credentials});
      const manifest=JSON.parse(await readFile(path.join(dir,'manifest.json'),'utf8'));
      if(manifest.status==='AwaitingExternalAI'){await patchProject(id,{status:'Awaiting AI',progress:58,stage:'Download the AI request, then paste the returned JSON',advanced:true,semiAutomated:true,outputs:{semiRequest:`/api/projects/${id}/assets/semi-automated-request.json`}});return;}
      await patchProject(id,{status:'Ready',progress:100,stage:'Advanced render ready',advanced:true,manifest,outputs:{preview:`/api/projects/${id}/assets/output.mp4`,thumbnail:`/api/projects/${id}/assets/thumbnail.jpg`,perception:`/api/projects/${id}/assets/perception.json`,audio:`/api/projects/${id}/assets/audio.json`,shots:`/api/projects/${id}/assets/shots.json`,crops:`/api/projects/${id}/assets/crop-keyframes.json`,subtitles:`/api/projects/${id}/assets/subtitles.ass`}});
    } catch(error) { let last={};try{last=JSON.parse(await readFile(path.join(dir,'status.json'),'utf8'));}catch{}await patchProject(id,{status:signal.aborted?'Cancelled':'Failed',progress:Number(last.progress||0),stage:signal.aborted?'Cancelled':String(last.stage||'Advanced engine failed'),error:error.message,errorInfo:classifyEngineError(error.message)}); throw error; }
  });
}

async function hydrateProject(project) {if(project.status==='Processing'&&project.advanced){try{const live=JSON.parse(await readFile(path.join(projectDir(project.id),'status.json'),'utf8'));return {...project,...live,status:live.stage==='Ready'?'Ready':project.status};}catch{}}return project;}
async function listProjects(){const ids=await readdir(PROJECTS).catch(()=>[]);const items=[];for(const id of ids){try{items.push(await hydrateProject(await loadProject(id)));}catch{}}return items.sort((a,b)=>String(b.createdAt).localeCompare(String(a.createdAt)));}

async function latestDiagnostic(id){
  const dir=projectDir(id),logsRoot=path.resolve(dir,'logs');const pointer=JSON.parse(await readFile(path.join(logsRoot,'current-run.json'),'utf8'));const runDir=path.resolve(String(pointer.folder||''));if(!runDir.startsWith(logsRoot+path.sep))throw new Error('Invalid run log location');
  const text=async(file,limit=120000)=>{try{const value=await readFile(file,'utf8');return value.slice(-limit);}catch{return null;}};const parse=async file=>{try{return JSON.parse(await readFile(file,'utf8'));}catch{return null;}};const jsonLines=async file=>(await text(file,160000)||'').split(/\r?\n/).filter(Boolean).slice(-500).map(line=>{try{return JSON.parse(line);}catch{return {message:line};}});
  return {schemaVersion:'1.3',applicationVersion:'4.8.0',projectId:id,createdAt:new Date().toISOString(),runSummary:await parse(path.join(runDir,'run-summary.json')),shareInstructions:await text(path.join(runDir,'SHARE-THIS-LOG.txt'),20000),modelUsage:await jsonLines(path.join(runDir,'model-usage.jsonl')),events:await jsonLines(path.join(runDir,'events.jsonl')),orchestratorReport:await parse(path.join(dir,'orchestrator-report.json')),executiveDecisionLedger:await parse(path.join(dir,'executive-decision-ledger.json')),worldModel:await parse(path.join(dir,'world-model.json')),directingDecisions:await parse(path.join(dir,'directing-decisions.json')),temporalCadence:await parse(path.join(dir,'temporal-cadence.json')),candidateUtility:await parse(path.join(dir,'candidate-utility.json')),storyModelRouting:await parse(path.join(dir,'story-model-routing.json')),storyCoordinateDossier:await parse(path.join(dir,'story-coordinate-dossier.json')),storyGraph:await parse(path.join(dir,'story-graph.json')),compositionPlan:await parse(path.join(dir,'composition-plan.json')),predictiveRisk:await parse(path.join(dir,'predictive-risk-report.json')),qualitySupervisor:await parse(path.join(dir,'quality-supervisor.json')),engineConsoleTail:await text(path.join(runDir,'engine-console.log'),80000)};
}

async function serveAsset(res, id, name) {
  const allowed = new Set(['proxy.mp4','preview.mp4','output.mp4','thumbnail.jpg','contact.jpg','plan.json','perception.json','audio.json','active-speakers.json','scenes.json','shots.json','crop-keyframes.json','subtitles.ass','manifest.json','status.json','corrections.json','semi-automated-request.json']);
  if (!allowed.has(name)) return json(res,404,{error:'Asset not found'});
  const file = path.join(projectDir(id),name); const info = await stat(file);
  const types = {'.mp4':'video/mp4','.jpg':'image/jpeg','.json':'application/json','.ass':'text/plain; charset=utf-8'};
  res.writeHead(200, {'content-type':types[path.extname(name)] || 'application/octet-stream','content-length':info.size,'accept-ranges':'bytes','cache-control':'no-store','access-control-allow-origin':'*'});
  createReadStream(file).pipe(res);
}

const server = http.createServer(async (req,res) => {
  const url = new URL(req.url, `http:${'//'}${req.headers.host || 'localhost'}`);
  try {
    if(req.method==='OPTIONS'){res.writeHead(204,{'access-control-allow-origin':'*','access-control-allow-methods':'GET,POST,PUT,DELETE,OPTIONS','access-control-allow-headers':'content-type,x-file-name,x-original-name'});return res.end();}
    if (req.method === 'GET' && url.pathname === '/api/health') return json(res,200,{ok:true,service:'clipperx-api',ffmpeg:commandExists('ffmpeg'),ffprobe:commandExists('ffprobe'),dataDir:DATA});
    if(req.method==='GET'&&url.pathname==='/api/diagnostics')return json(res,200,diagnoseEngine());
    if(req.method==='POST'&&url.pathname==='/api/diagnostics/repair')return json(res,202,{ok:true,repair:startEngineRepair()});
    if (req.method === 'GET' && url.pathname === '/api/providers') return json(res,200,{providers:PROVIDERS});
    if (req.method === 'POST' && url.pathname === '/api/providers/validate') return json(res,200,await validateProvider(await readJson(req)));
    if (req.method === 'GET' && url.pathname === '/api/projects') return json(res,200,{projects:await listProjects()});
    if (req.method === 'GET' && url.pathname === '/api/queue') return json(res,200,queue.snapshot());
    if (req.method === 'POST' && url.pathname === '/api/projects') {
      const body = await readJson(req); const id = crypto.randomUUID().slice(0,8); await mkdir(projectDir(id),{recursive:true});
      const project = await saveProject({id,name:String(body.name || 'Untitled project').slice(0,120),profile:String(body.profile || 'Podcast'),provider:body.provider || null,model:body.model || null,semiAutomated:body.semiAutomated===true,status:'Draft',progress:0,stage:'Waiting for video',createdAt:new Date().toISOString(),updatedAt:new Date().toISOString()});
      return json(res,201,{project});
    }
    let match = url.pathname.match(/^\/api\/projects\/([\w-]+)$/);
    if (req.method === 'GET' && match) {
      const project=await hydrateProject(await loadProject(match[1]));
      return json(res,200,{project});
    }
    match = url.pathname.match(/^\/api\/projects\/([\w-]+)\/logs\/latest$/);
    if(req.method==='GET'&&match){const body=Buffer.from(JSON.stringify(await latestDiagnostic(match[1]),null,2));res.writeHead(200,{'content-type':'application/json; charset=utf-8','content-length':body.length,'content-disposition':`attachment; filename="clipperx-${match[1]}-diagnostic.json"`,'cache-control':'no-store','access-control-allow-origin':'*'});return res.end(body);}
    if (req.method === 'DELETE' && match) { await rm(projectDir(match[1]),{recursive:true,force:true}); return json(res,200,{ok:true}); }
    match = url.pathname.match(/^\/api\/projects\/([\w-]+)\/video$/);
    if (req.method === 'PUT' && match) {
      const id = match[1]; const project = await loadProject(id); const length = Number(req.headers['content-length'] || 0); if (length > MAX_UPLOAD) return json(res,413,{error:'Video exceeds upload limit'});
      const rawName = String(req.headers['x-file-name'] || 'video.mp4');
      const name = safeName(decodeURIComponent(rawName)); const target = path.join(projectDir(id),name); let received = 0;
      await new Promise((resolve,reject) => { const output=createWriteStream(target); req.on('data',(chunk)=>{received+=chunk.length;if(received>MAX_UPLOAD){req.destroy();output.destroy();reject(new Error('Video exceeds upload limit'));}}); req.pipe(output); output.on('finish',resolve); output.on('error',reject); req.on('error',reject); });
      await saveProject({...project,inputFile:name,originalFileName:req.headers['x-original-name'] || name,status:'Uploaded',stage:'Ready to analyze'}); return json(res,200,{ok:true,bytes:received});
    }
    match = url.pathname.match(/^\/api\/projects\/([\w-]+)\/analyze$/);
    if (req.method === 'POST' && match) {
      const credentials=await readJson(req); const project=await loadProject(match[1]); if(!project.inputFile) return json(res,400,{error:'Upload a video first'});
      if(credentials.engine==='advanced'){await patchProject(match[1],{advanced:true,semiAutomated:credentials.semiAutomated===true});await runAdvancedJob(match[1],credentials);}
      else runPipeline(match[1],credentials);
      return json(res,202,{ok:true,projectId:match[1],engine:credentials.engine==='advanced'?'advanced':'phase0'});
    }
    match = url.pathname.match(/^\/api\/projects\/([\w-]+)\/cancel$/);
    if(req.method==='POST'&&match){await writeFile(path.join(projectDir(match[1]),'CANCEL'),'cancelled');queue.cancel(match[1]);await patchProject(match[1],{status:'Cancelled',stage:'Cancelling',progress:0});return json(res,200,{ok:true});}
    match = url.pathname.match(/^\/api\/projects\/([\w-]+)\/corrections$/);
    if(req.method==='PUT'&&match){const body=await readJson(req);if(!Array.isArray(body.corrections))return json(res,400,{error:'corrections must be an array'});await writeFile(path.join(projectDir(match[1]),'corrections.json'),JSON.stringify(body.corrections,null,2));return json(res,200,{ok:true,count:body.corrections.length});}
    match = url.pathname.match(/^\/api\/projects\/([\w-]+)\/semi-response$/);
    if(req.method==='POST'&&match){const body=await readJson(req);let value=body.response??body;if(typeof value==='string'){const cleaned=value.replace(/^```(?:json)?/i,'').replace(/```$/,'').trim(),start=cleaned.indexOf('{'),end=cleaned.lastIndexOf('}');if(start<0||end<start)return json(res,400,{error:'Paste the complete JSON object returned by the external AI'});value=JSON.parse(cleaned.slice(start,end+1));}if(!value||typeof value!=='object'||!Array.isArray(value.events))return json(res,400,{error:'The response must be a JSON object containing an events array'});await writeFile(path.join(projectDir(match[1]),'semi-automated-response.json'),JSON.stringify(value,null,2));await patchProject(match[1],{status:'Processing',progress:58,stage:'Validating pasted AI response',error:null});await runAdvancedJob(match[1],{engine:'advanced',semiAutomated:true});return json(res,202,{ok:true});}
    match = url.pathname.match(/^\/api\/projects\/([\w-]+)\/assets\/([\w.-]+)$/);
    if (req.method === 'GET' && match) return await serveAsset(res,match[1],match[2]);
    return json(res,404,{error:'Route not found'});
  } catch (error) { return json(res,error.code === 'ENOENT' ? 404 : 400,{error:error.message}); }
});
server.listen(PORT,'127.0.0.1',()=>console.log(`ClipperX API ready at http://localhost:${PORT}`));
