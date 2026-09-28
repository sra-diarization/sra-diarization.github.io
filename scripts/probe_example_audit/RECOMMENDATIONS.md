# Probe-linked qualitative examples

These are deliberately selected joint improvements, not evidence of a general or causal sample-level relation. The demo displays the three OV2 cases and the Two1 Single case below. Two12, One6 and the counterexample are retained in the data and audit but excluded from the page.

Existing 2-s out-of-fold probe predictions reproduce the paper's aggregate MAEs. All values below average the three probe seeds; no best seed is selected. Every OV2 case in this table improves Separation-2 at F in all three seeds.

| Recording | Interval (s) | Label (deg) | F-probe MAE, baseline -> SRA (deg) | Local DER, baseline -> SRA (%) |
|---|---:|---:|---:|---:|
| mvad_Two5 | 36-38 | 33.87 | 24.37 -> 5.21 | 88.00 -> 0.00 |
| mvad_Three3 | 24.5-26.5 | 22.44 | 20.02 -> 9.02 | 9.50 -> 0.00 |
| mvad_Three2 | 19.5-21.5 | 21.45 | 28.35 -> 13.05 | 50.00 -> 35.50 |

- mvad_Two5__036.000: Miss decreases 88.00% -> 0.00%; both reference speakers are recovered.
- mvad_Three3__024.500: Miss decreases 9.50% -> 0.00%; a 0.38-s gap in the second speaker is recovered.
- mvad_Three2__019.500: Confusion decreases 25.00% -> 2.50%, while Miss increases 25.00% -> 33.00%; this is a net improvement with a tradeoff.

The label is the existing Separation-2 target (camera-projected angular separation). It should not be replaced by the world-coordinate azimuth separation displayed by the top-view map; those definitions can differ.

## Additional Single cases

Two1 (9.5-11.5 s) has one active reference speaker. Azimuth F MAE changes 15.04 -> 4.06 degrees, Elevation 6.75 -> 3.92 degrees, and Distance 0.710 -> 0.410 m. DER changes 30.00 -> 0.00%, removing 0.600 speaker-seconds of false alarm. Each probe improves in two seeds; the third is worse for Azimuth/Distance and tied for Elevation. In the fixed 3.5-19.5 s context, DER is 20.29 -> 15.20%.

Two12 (27.5-29.5 s) improves Azimuth F MAE from 31.66 to 6.66 degrees in all three seeds, and DER from 14.79 to 11.75%. Its frame-sampled probe cohort is Single, but exact RTTM scoring includes 0.010658 s of overlap; all frames are retained. Its fixed 21.5-37.5 s context improves DER from 6.83 to 5.89%; reference positions are image-only. It was removed from the page because the diarization improvement is visually modest, and remains in the packaged data and audit.

One6 (16.5-18.5 s) has one active reference speaker. Azimuth F MAE changes 8.76 -> 2.09 degrees, improving in all three seeds. DER changes 13.95 -> 0.00%, removing 0.279 speaker-seconds of miss. The fixed 10.5-26.5 s context instead worsens from 14.74 to 17.57%; only the highlighted window is a joint improvement. It was removed from the page because full-context DER worsens; both scores remain in the packaged data and audit.

Probe extraction uses isolated 2-s inputs, whereas the existing diarization predictions use longer inference windows and reconstruction. Matching timestamps does not make these the same forward pass.

## Population context

Across all 393 overlapping 2-s OV2 windows, 31 improve on both axes and 39 improve probe error while DER worsens. These windows overlap in time, so their counts are not independent trial counts.
The prior within-recording association is rho=-0.028, 95% recording-cluster CI [-0.179, 0.140]. It does not establish a general positive association.

For a demo, retain a longer audio context with the 2-s evaluation interval explicitly marked. Show its reference label, all three seed predictions or their MAE, and time-aligned diarization errors. Do not label the longer-context DER as the 2-s probe-window DER. Retain counterexamples in the audit.

Reproduce: `.conda/spatialrole/bin/python sra-diarization.github.io/scripts/audit_probe_examples.py`
