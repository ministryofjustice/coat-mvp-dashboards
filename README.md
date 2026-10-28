# COAT MVP Dashboards
Platform to create Streamlit MVP dashboards.

# Running a dashboard locally

To run your Streamlit dashboard locally:
```
make run-local DASHBOARD=coh_dashboard
```

To run a dashboard in a Docker container:
```
make build DASHBOARD=coh_dashboard
make run DASHBOARD=coh_dashboard
```

To stop the container:
```
make stop DASHBOARD=coh_dashboard
```

# Deploying your dashboard using the platform

Example [dashboard PR](https://github.com/ministryofjustice/coat-mvp-dashboards/pull/8)

# Dashboards

- https://coat-mvp-dashboards-dev.cloud-platform.service.justice.gov.uk/showback-report/
- https://coat-mvp-dashboards-dev.cloud-platform.service.justice.gov.uk/coh-dashboard/