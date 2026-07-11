from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class Config:
    analysis_width: int = 480
    sample_fps: float = 4.0
    lookahead_seconds: float = 1.5
    output_width: int = 1080
    output_height: int = 1920
    crf: int = 20
    cut_threshold: float = 0.48
    candidate_count: int = 31
    velocity_cost: float = 0.55
    acceleration_cost: float = 1.25
    switch_cost: float = 0.18
    max_pan_per_second: float = 0.32
    smoothing_passes: int = 3

    def validate(self) -> None:
        if self.analysis_width < 160:
            raise ValueError("analysis_width must be at least 160")
        if self.sample_fps <= 0:
            raise ValueError("sample_fps must be positive")
        if self.candidate_count < 3:
            raise ValueError("candidate_count must be at least 3")
        if self.output_width <= 0 or self.output_height <= 0:
            raise ValueError("output dimensions must be positive")
        if self.output_width / self.output_height >= 1:
            raise ValueError("output must be portrait")
