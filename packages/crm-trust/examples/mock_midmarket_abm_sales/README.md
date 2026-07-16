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
