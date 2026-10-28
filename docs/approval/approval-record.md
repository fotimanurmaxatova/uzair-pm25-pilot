# Written approval record

- Project: UzAir: Predicting Modelled PM2.5 from Weather in Uzbek Cities
- Decision: Approved
- From: Sanjar Bekov (Module Leader)
- Route: University email
- Approval date: 28.10.2026
- Scope: Seven-day exploratory pilot as described in Version 4 plus the addendum

## Full text of the approval email
````
Dear Fotima,
Thank you for the addendum.
Decision: Approved.
I approve “UzAir: Predicting Modelled PM2.5 from Weather in Uzbek Cities” as the seven-day exploratory pilot described in Version 4, with this addendum replacing the corresponding sections. You may begin assessed collection on 2 November 2026, once the collection MVP is working.
Please retain the following controls during implementation:
Apply cut-offs using actual receipt timestamps. Your revised calendar is consistent, including the maximum of 336 test pairs. The “cut-off minus seven hours” rule assumes timely collection; delayed outcomes remain ineligible if received after fitting. Report actual usable pairs after missingness and lag construction, and preserve the original observation versions and prediction timestamps.
Freeze model choices before testing. Select the primary model and the full/no-weather comparison using training and cross-validation only. Compare matched models on the same eligible forecast origins, with comparable tuning procedures. Keep the final configuration locked after 6 November, and do not use the weekend test results to select a preferred configuration.
Keep Rules A and B exploratory. Passing either rule supports the case for a longer evaluation only. It does not establish a causal weather effect or general forecasting superiority. If a required sensitivity analysis cannot be estimated, report the screening result as inconclusive. Q4 has only five weekday clusters, which should be stated alongside its uncertainty estimates.
Preserve the collection and scope limits. The approved target is at least 1,000 valid scheduled rows from the maximum of 1,344. Report coverage and eligible pairs separately, retain the agreed fallback, and keep pilot and recovery records outside the main analysis. Continue the analysis restricted to native three-hourly times: CAMS global data has three-hourly resolution, so hourly polling does not produce independent hourly measurements.
Record the exact class-hours definition, feature specifications and screening rules in the repository before assessed collection. Retain the existing database, queries, visualisations, tests, reproducibility arrangements and LO1, LO2 and LO5 evidence plan.
Regarding checkpoints, the current Assessment 2 brief requires no separate Week 7–10 checkpoint forms or submissions. All four development checkpoints remain compulsory. Include their exact historical commit hashes and evidence records with the final report submitted in Teaching Week 12, by the date and time published on the LMS.
No further proposal revision is required for this approved scope. Keep this email as your written approval record.
Kind regards,
Sanjar Bekov
````
