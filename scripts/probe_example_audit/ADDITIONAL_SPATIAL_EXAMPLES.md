# Additional Azimuth and Distance examples

Existing F-probe OOF predictions, all three seeds; same 2-s local RTTM score. Fixed 16-s context beginning 6 s before each probe window, clipped to recording boundaries on a 0.5-s grid. Context endpoints are not optimized by DER. Exact RTTM activity is checked separately from the frame-sampled probe manifest.

Values are S-DiariZen -> S-DiariZen-SRA. Probe values are three-seed F MAE, not a selected seed. These are outcome-selected qualitative candidates. No demo assets or model outputs are changed.

| File | Probe window (s) | Task | F MAE | Local DER (%) | Context (s) | Context DER (%) | Improved/tied/worse seeds | Exact Single | Position coverage |
|---|---:|---|---:|---:|---:|---:|---|---|---:|
| One3.wav | 53.5-55.5 | Azimuth | 25.77 -> 14.66 deg | 4.65 -> 0.00 | 44-60 | 52.20 -> 42.45 | 2/0/1 | True | 100.0% |
| Two12.wav | 27.5-29.5 | Azimuth | 31.66 -> 6.66 deg | 14.79 -> 11.75 | 21.5-37.5 | 6.83 -> 5.89 | 3/0/0 | False | 100.0% |
| One7.wav | 22-24 | Distance | 0.425 -> 0.358 m | 6.65 -> 5.65 | 16-32 | 10.88 -> 9.73 | 2/1/0 | True | 100.0% |

- One3 removes 0.093 speaker-seconds of miss in the probe window. Its long context improves but still has high DER; only image positions are available.
- Two12 removes 0.061 speaker-seconds of false alarm. Its probe manifest labels the window Single, but exact RTTM scoring finds 0.010658 s of overlap at the edge. The packaged data explicitly validates this activity distribution and retains all frames. It is excluded from the page because the diarization improvement is visually modest.
- One7 removes only 0.020 speaker-seconds of miss. Distance improves in two seeds with one tie; Azimuth is unchanged and Elevation worsens. It is not a multi-attribute win.
- Other Distance joint-improvement windows are adjacent to the existing Two1 example or have worse fixed-context DER (Two4 and Two5). One6 remains excluded because its fixed-context DER worsens.
- Every candidate and its context result, including rejected candidates, is saved in additional_spatial_candidates.csv.

Reproduce: `.conda/spatialrole/bin/python sra-diarization.github.io/scripts/find_additional_probe_examples.py`
