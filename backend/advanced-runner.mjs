import { spawn,spawnSync } from 'node:child_process';
import path from 'node:path';
import { writeFile,rm,mkdir } from 'node:fs/promises';
import { createWriteStream } from 'node:fs';

const terminateTree=(child)=>{if(!child?.pid)return;if(process.platform==='win32')spawnSync('taskkill',['/pid',String(child.pid),'/t','/f'],{windowsHide:true,stdio:'ignore'});else{try{process.kill(-child.pid,'SIGTERM');}catch{try{child.kill('SIGTERM');}catch{}}}};
export function runAdvanced({root,projectDir,input,profile='Podcast',corrections,semantic,signal,credentials={}}) {
  return new Promise(async(resolve,reject)=>{
    await rm(path.join(projectDir,'CANCEL'),{force:true}).catch(()=>{});
    const runId=`run-${new Date().toISOString().replace(/[:.]/g,'-')}`;const logDir=path.join(projectDir,'logs',runId);await mkdir(logDir,{recursive:true});const consoleLog=createWriteStream(path.join(logDir,'engine-console.log'),{flags:'a'});consoleLog.write(`${new Date().toISOString()} launcher started\n`);
    const args=['-m','engine.pipeline','--input',input,'--output-dir',projectDir,'--profile',profile,'--corrections',corrections];if(semantic)args.push('--semantic',semantic);
    const cpu=Math.max(1,Number(process.env.CLIPPERX_WORKER_THREADS||Math.min(4,Math.max(1,(Number(process.env.NUMBER_OF_PROCESSORS)||4)-1))));
    const env={...process.env,CLIPPERX_PROVIDER:credentials.provider||'',CLIPPERX_MODEL:credentials.model||'',CLIPPERX_API_KEY:credentials.apiKey||'',CLIPPERX_BASE_URL:credentials.baseUrl||'',CLIPPERX_SEMI_AUTOMATED:credentials.semiAutomated?'1':'0',CLIPPERX_RUN_ID:runId,CLIPPERX_LOG_DIR:logDir,OMP_NUM_THREADS:String(cpu),MKL_NUM_THREADS:String(cpu),OPENBLAS_NUM_THREADS:String(cpu),NUMEXPR_NUM_THREADS:String(cpu),PYTHONUNBUFFERED:'1'};
    const child=spawn(process.env.CLIPPERX_PYTHON||(process.platform==='win32'?'python':'python3'),args,{cwd:root,env,stdio:['ignore','pipe','pipe'],windowsHide:true,detached:process.platform!=='win32'});let err='';let settled=false;const timeoutMs=Math.max(60_000,Number(process.env.CLIPPERX_JOB_TIMEOUT_MS||21_600_000));
    child.stdout.on('data',chunk=>consoleLog.write(`[stdout] ${chunk}`));child.stderr.on('data',chunk=>{consoleLog.write(`[stderr] ${chunk}`);err+=chunk;if(err.length>30000)err=err.slice(-30000);});
    const cancel=()=>{writeFile(path.join(projectDir,'CANCEL'),'cancelled').catch(()=>{});terminateTree(child);};if(signal.aborted)cancel();else signal.addEventListener('abort',cancel,{once:true});
    const timer=setTimeout(()=>{if(!settled){writeFile(path.join(projectDir,'CANCEL'),'timeout').catch(()=>{});terminateTree(child);}},timeoutMs);timer.unref?.();
    child.on('error',error=>{if(settled)return;settled=true;clearTimeout(timer);consoleLog.end(`${new Date().toISOString()} launcher error: ${error.message}\n`);reject(error);});child.on('close',code=>{if(settled)return;settled=true;clearTimeout(timer);signal.removeEventListener('abort',cancel);consoleLog.end(`${new Date().toISOString()} launcher exited ${code}\n`);if(code===0)return resolve();if(signal.aborted)return reject(new Error('Cancelled'));const lines=err.split(/\r?\n/).filter(Boolean);const useful=lines.filter(line=>/error|failed|missing|could not|traceback|insufficient/i.test(line)).slice(-5);reject(new Error(`Advanced engine exited ${code}. ${(useful.length?useful:lines.slice(-5)).join(' | ').slice(0,1200)}`));});
  });
}
