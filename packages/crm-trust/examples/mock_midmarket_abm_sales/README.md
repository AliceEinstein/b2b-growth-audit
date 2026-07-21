# Mock Mid-Market ABM + Sales CRM

Synthetic, reusable CRM fixture for CRM Audit and related tests.

- 360 contacts
- 60 companies
- 36 deals
- 8 owners
- 2 pipelines
- contact-company and deal associations
- intentional association, attribution, ownership, pipeline, and property-governance gaps
- synthetic PII and instruction-shaped CRM values exist only in raw/ to exercise sanitization and untrusted-data handling

Run deterministic measurements:

```bash
python -m scripts.run_audit_measurements --run examples/mock_midmarket_abm_sales
```

Then validate findings and continue with the host-agent judgment/review/report stages.

The repository also includes a final-gate-passed Northstar Systems mock report
generated from this synthetic portal. Open `crm_trust_report.html` for the
decision-maker view. Company/Deal labels and HubSpot links are synthetic, but
the package follows the same confidential-report handling rules as a live run.

Verify that the checked-in report still matches its approved artifacts:

```bash
python -m scripts.verify_final_gate --run examples/mock_midmarket_abm_sales
```
