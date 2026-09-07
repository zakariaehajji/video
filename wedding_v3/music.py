"""Music analysis for wedding montage v3 using librosa."""

from __future__ import annotations

import argparse
import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import librosa
import numpy as np


DEFAULT_SR = 22050
BEATS_PER_DOWNBEAT = 4
BEATS_PER_PHRASE = 8
TOP_PEAK_COUNT = 8
SECTION_LABELS = ("intro", "build", "chorus", "peak", "outro", "verse")
HOP_LENGTH = 512
MIN_SECTION_SECONDS = 5.0


def _normalize(arr: np.ndarray) -> np.ndarray:
    arr = np.asarray(arr, dtype=float)
    lo, hi = float(arr.min()), float(arr.max())
    if hi - lo < 1e-8:
        return np.zeros_like(arr)
    return (arr - lo) / (hi - lo)


def _estimate_section_count(duration: float) -> int:
    if duration < 30:
        return 3
    if duration < 90:
        return 5
    if duration < 180:
        return 6
    return int(np.clip(duration / 30, 4, 8))


def _label_sections(sections: list[dict[str, Any]], duration: float) -> None:
    if not sections:
        return

    energies = np.array([s["mean_energy"] for s in sections], dtype=float)
    positions = np.array([s["start"] / max(duration, 1e-6) for s in sections], dtype=float)
    labels = ["verse"] * len(sections)

    labels[0] = "intro" if energies[0] <= np.median(energies) else "build"
    if len(sections) > 1:
        labels[-1] = "outro"

    peak_idx = int(np.argmax(energies))
    labels[peak_idx] = "peak"

    threshold = float(np.percentile(energies, 70))
    for i, energy in enumerate(energies):
        if i == peak_idx:
            continue
        if energy >= threshold and 0.2 < positions[i] < 0.85:
            labels[i] = "chorus"

    for i in range(1, len(sections) - 1):
        if labels[i] != "verse":
            continue
        rising = energies[i] > energies[i - 1]
        early = positions[i] < 0.55
        if rising and early:
            labels[i] = "build"

    for section, label in zip(sections, labels):
        section["label"] = label


@dataclass
class MusicAnalysis:
    """Analyze a music track for montage timing cues."""

    audio_path: Path
    sr: int = DEFAULT_SR
    beats_per_downbeat: int = BEATS_PER_DOWNBEAT
    beats_per_phrase: int = BEATS_PER_PHRASE
    top_peak_count: int = TOP_PEAK_COUNT
    _result: dict[str, Any] = field(default_factory=dict, init=False, repr=False)

    def __post_init__(self) -> None:
        self.audio_path = Path(self.audio_path)

    def analyze(self) -> dict[str, Any]:
        y, sr = librosa.load(str(self.audio_path), sr=self.sr, mono=True)
        duration = float(librosa.get_duration(y=y, sr=sr))

        tempo, beat_frames = librosa.beat.beat_track(y=y, sr=sr, units="frames")
        beat_times = librosa.frames_to_time(beat_frames, sr=sr).astype(float).tolist()
        bpm = float(np.atleast_1d(tempo)[0])

        downbeat_times = beat_times[:: self.beats_per_downbeat]

        onset_env = librosa.onset.onset_strength(y=y, sr=sr, hop_length=HOP_LENGTH)
        frame_times = librosa.frames_to_time(np.arange(len(onset_env)), sr=sr, hop_length=HOP_LENGTH)
        smooth_win = max(8, int(0.35 * sr / 512))
        energy_frames = np.convolve(onset_env, np.ones(smooth_win) / smooth_win, mode="same")
        energy_frames = _normalize(energy_frames)

        curve_step = max(1, len(frame_times) // 400)
        energy_curve = {
            "times": frame_times[::curve_step].astype(float).tolist(),
            "values": energy_frames[::curve_step].astype(float).tolist(),
        }

        sections = self._segment_sections(y, sr, duration, frame_times, energy_frames)
        phrases = self._build_phrases(beat_times, duration)
        peaks = self._find_peaks(frame_times, energy_frames)

        self._result = {
            "source": str(self.audio_path.resolve()),
            "duration": round(duration, 3),
            "sr": sr,
            "bpm": round(bpm, 2),
            "beat_times": [round(t, 3) for t in beat_times],
            "downbeat_times": [round(t, 3) for t in downbeat_times],
            "energy_curve": energy_curve,
            "sections": sections,
            "phrases": phrases,
            "peaks": peaks,
        }
        return self._result

    def _segment_sections(
        self,
        y: np.ndarray,
        sr: int,
        duration: float,
        frame_times: np.ndarray,
        energy_frames: np.ndarray,
    ) -> list[dict[str, Any]]:
        n_sections = _estimate_section_count(duration)
        boundary_frames = self._section_boundary_frames(y, sr, duration, energy_frames, n_sections)
        boundary_times = librosa.frames_to_time(boundary_frames, sr=sr, hop_length=HOP_LENGTH).astype(float)
        boundary_times[0] = 0.0
        boundary_times[-1] = duration

        sections: list[dict[str, Any]] = []
        for i, (start_idx, end_idx) in enumerate(zip(boundary_frames[:-1], boundary_frames[1:])):
            start_t = float(boundary_times[i])
            end_t = float(boundary_times[i + 1])
            if end_t - start_t < 0.5:
                continue
            seg_energy = energy_frames[start_idx : end_idx + 1]
            sections.append(
                {
                    "start": round(start_t, 3),
                    "end": round(end_t, 3),
                    "mean_energy": round(float(np.mean(seg_energy)), 4),
                }
            )

        if not sections:
            sections = [
                {
                    "start": 0.0,
                    "end": round(duration, 3),
                    "mean_energy": round(float(np.mean(energy_frames)), 4),
                }
            ]

        _label_sections(sections, duration)
        return sections

    def _section_boundary_frames(
        self,
        y: np.ndarray,
        sr: int,
        duration: float,
        energy_frames: np.ndarray,
        n_sections: int,
    ) -> list[int]:
        chroma = librosa.feature.chroma_cqt(y=y, sr=sr, hop_length=HOP_LENGTH)
        n_frames = min(chroma.shape[1], len(energy_frames))
        chroma = chroma[:, :n_frames]
        energy = energy_frames[:n_frames]

        chroma_novelty = np.sum(np.abs(np.diff(chroma, axis=1)), axis=0)
        energy_novelty = np.abs(np.diff(energy))
        novelty = _normalize(chroma_novelty[: len(energy_novelty)] + energy_novelty)

        min_gap_frames = max(1, int(MIN_SECTION_SECONDS * sr / HOP_LENGTH))
        frame_times = librosa.frames_to_time(np.arange(n_frames), sr=sr, hop_length=HOP_LENGTH)

        target_times = np.linspace(0.0, duration, n_sections + 1)[1:-1]
        boundary_frames = [0]
        search_radius = max(8, int(4.0 * sr / HOP_LENGTH))

        for target in target_times:
            center = int(np.searchsorted(frame_times, target))
            lo = max(1, center - search_radius)
            hi = min(len(novelty) - 1, center + search_radius)
            if lo >= hi:
                continue
            peak = lo + int(np.argmax(novelty[lo:hi]))
            if peak - boundary_frames[-1] >= min_gap_frames:
                boundary_frames.append(peak)

        boundary_frames.append(n_frames - 1)

        if len(boundary_frames) <= 2:
            boundary_frames = [
                int(round(t * sr / HOP_LENGTH))
                for t in np.linspace(0.0, duration, n_sections + 1)
            ]
            boundary_frames[0] = 0
            boundary_frames[-1] = n_frames - 1

        return sorted(set(boundary_frames))

    def _build_phrases(self, beat_times: list[float], duration: float) -> list[dict[str, Any]]:
        if not beat_times:
            return []

        phrases: list[dict[str, Any]] = []
        for i in range(0, len(beat_times), self.beats_per_phrase):
            start = beat_times[i]
            end_idx = min(i + self.beats_per_phrase - 1, len(beat_times) - 1)
            end = beat_times[end_idx]
            if i + self.beats_per_phrase < len(beat_times):
                end = beat_times[i + self.beats_per_phrase]
            else:
                end = duration
            phrases.append(
                {
                    "start": round(start, 3),
                    "end": round(end, 3),
                    "beat_start_index": i,
                    "beat_count": min(self.beats_per_phrase, len(beat_times) - i),
                }
            )
        return phrases

    def _find_peaks(self, frame_times: np.ndarray, energy_frames: np.ndarray) -> list[dict[str, Any]]:
        peak_idx = librosa.util.peak_pick(
            energy_frames,
            pre_max=5,
            post_max=5,
            pre_avg=5,
            post_avg=5,
            delta=0.05,
            wait=10,
        )
        if len(peak_idx) == 0:
            peak_idx = np.argsort(energy_frames)[-self.top_peak_count :]

        ranked = sorted(
            ((float(frame_times[i]), float(energy_frames[i])) for i in peak_idx),
            key=lambda item: item[1],
            reverse=True,
        )[: self.top_peak_count]
        ranked.sort(key=lambda item: item[0])

        return [{"time": round(t, 3), "energy": round(e, 4)} for t, e in ranked]

    def to_dict(self) -> dict[str, Any]:
        if not self._result:
            self.analyze()
        return self._result

    def to_json(self, path: Path | str | None = None, indent: int = 2) -> str:
        payload = self.to_dict()
        text = json.dumps(payload, indent=indent)
        if path is not None:
            out = Path(path)
            out.parent.mkdir(parents=True, exist_ok=True)
            out.write_text(text, encoding="utf-8")
        return text


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Analyze music for wedding montage v3.")
    parser.add_argument("audio", type=Path, help="Path to an audio file (mp3, wav, etc.)")
    parser.add_argument(
        "--out",
        type=Path,
        default=None,
        help="Write JSON analysis to this path",
    )
    parser.add_argument("--sr", type=int, default=DEFAULT_SR, help="Sample rate for analysis")
    args = parser.parse_args(argv)

    analysis = MusicAnalysis(args.audio, sr=args.sr)
    result = analysis.analyze()

    if args.out:
        analysis.to_json(args.out)
        print(f"Wrote {args.out}")
    else:
        print(json.dumps(result, indent=2))

    print(
        f"BPM={result['bpm']}  sections={len(result['sections'])}  "
        f"peaks={[p['time'] for p in result['peaks'][:5]]}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
