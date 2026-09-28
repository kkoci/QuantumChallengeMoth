\# QuantumChallengeMoth



Moth Hack 2026 — challenges \*\*09 (Quantum-native 1)\*\* and \*\*10 (Quantum-native 2)\*\*.



A measure-once, render-many audio pipeline built on Moth's

\[`retrocausal-echo-v1`](https://platform.mothquantum.com) engine — a multi-tap

delay whose tap map is measured on a quantum computer (Aer simulation by

default, no IBM hardware required). Negative tap amplitudes invert, reverse,

or rotate the signal depending on `negative\_mode`, giving echoes that don't

behave like an ordinary classical delay.



\## The idea



Quantum measurement is the expensive, slow part; audio rendering is cheap and

fast. So this splits into two phases:



1\. \*\*Measure\*\* — submit a job with no audio input. The engine measures a

&#x20;  quantum impulse response (IR) and hands back a portable `trajectory` JSON

&#x20;  envelope, a reference WAV of the IR alone, and the full tap map (time,

&#x20;  level, pan, complex amplitude, polarity per tap).

2\. \*\*Render\*\* — reuse that saved IR against real audio. Passing the `ir`

&#x20;  asset id back in skips re-measurement entirely — per Moth's own docs,

&#x20;  \*"re-render a measured response ... without paying for the measurement

&#x20;  again."\* One measurement, unlimited renders.



This is also the fix for why a naive "call the quantum API per audio event"

design doesn't work: Moth's API is asynchronous and poll-based, with no

sub-second guarantee. Baking the quantum work into a reusable asset ahead of

time is what makes it usable in something like a plugin or sampler.



\## Repo contents



\- `retrocausal\_pipeline.py` — CLI with three commands:

&#x20; - `measure` — runs a preset grid sweeping `theta\_x` (how "quantum" the

&#x20;   taps are — low = regular taps, high = erasure/inversion) and `theta\_zz`

&#x20;   (coupling; \~0.25π is the engine's own documented sparse setting).

&#x20; - `sweep --center X --steps N --span S` — finer search around one

&#x20;   `theta\_x` value, holding everything else fixed.

&#x20; - `render <audio file>` — uploads a clip and renders it through every

&#x20;   saved preset/sweep point, reusing each `ir\_asset\_id`. Auto-trims input

&#x20;   to fit the engine's 180-second (including tail) render cap.

\- `challenge\_10\_notebook.ipynb` — the full workflow narrated end to end:

&#x20; one measurement, tap map inspection, one reuse-render, playback.

\- `output/presets.json` — manifest of every measured preset/sweep point and

&#x20; its `ir\_asset\_id`.

\- `output/<preset>/` — per preset: `ir\_reference.wav`, `ir.json`,

&#x20; `taps.json`, and the rendered output audio.

\- `requirements.txt`



\## Running it



```bash

export MOTH\_API\_KEY="moth\_..."       # PowerShell: $env:MOTH\_API\_KEY="moth\_..."

pip install -r requirements.txt



python retrocausal\_pipeline.py measure

python retrocausal\_pipeline.py sweep --center 2.4 --steps 5 --span 0.8

python retrocausal\_pipeline.py render path/to/your\_audio.wav

```



\## Result



A sweep across `theta\_x` (six base presets plus five sweep points around

2.4) came out clearest at \*\*`theta\_x = 2.6`\*\* — deep in the erasure/

inversion regime the engine's docs describe, where the echo stops sounding

like an ordinary delay. That's the preset used in the notebook and in the

02 (Make it audible) submission.



\## Credits



Built on Moth Quantum's Atlas platform and the `retrocausal-echo-v1` /

`otoc-echo-v1` engines (`quantum-echo` library).

