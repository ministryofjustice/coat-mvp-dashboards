run-local:
	python3 -m venv .venv && source .venv/bin/activate
	pip install -r requirements.txt
	streamlit run ./dashboards/$(DASHBOARD)/app.py

build:
	docker build --build-arg DASHBOARD=$(DASHBOARD) -t $(DASHBOARD):latest .

run:
	docker run -d -p 8501:8501 \
		--name $(DASHBOARD) \
		-e AUTH0_DOMAIN="${AUTH0_DOMAIN}" \
		-e AUTH0_CLIENT_ID="${AUTH0_CLIENT_ID}" \
		-e AUTH0_CLIENT_SECRET="${AUTH0_CLIENT_SECRET}" \
		-e APP_BASE_URL="http://localhost:8501" \
		-e AUTH_DISABLED=true \
		$(DASHBOARD):latest

stop:
	docker rm -f $(DASHBOARD)

helm-deploy:
	helm upgrade coat-mvp-dashboards \
        helm/coat-mvp-dashboards \
        --install \
        --force \
		--server-side=false \
        --wait \
        --timeout 10m \
        --namespace coat-mvp-dashboards-dev \
        --values=helm/coat-mvp-dashboards/values-dev.yaml \
        --set app.deployment.dashboards.coh_dashboard.image.repository=levgorbunov1/coh_dashboard \
        --set app.deployment.dashboards.coh_dashboard.image.tag=latest \
		--set app.deployment.dashboards.showback_report.image.repository=levgorbunov1/showback_report \
        --set app.deployment.dashboards.showback_report.image.tag=latest \
		--set app.deployment.env.AUTH0_DOMAIN="${AUTH0_DOMAIN}" \
		--set app.deployment.env.AUTH0_CLIENT_ID="${AUTH0_CLIENT_ID}" \
        --set app.deployment.env.AUTH0_CLIENT_SECRET="${AUTH0_CLIENT_SECRET}"

helm-template:
	helm template coat-mvp-dashboards \
        helm/coat-mvp-dashboards \
        --namespace coat-mvp-dashboards-dev \
        --values=helm/coat-mvp-dashboards/values-dev.yaml \
        --set app.deployment.dashboards.coh_dashboard.image.repository=levgorbunov1/coh_dashboard \
        --set app.deployment.dashboards.coh_dashboard.image.tag=latest \
		--set app.deployment.dashboards.showback_report.image.repository=levgorbunov1/showback_report \
        --set app.deployment.dashboards.showback_report.image.tag=latest \
		--set app.deployment.env.AUTH0_DOMAIN="${AUTH0_DOMAIN}" \
		--set app.deployment.env.AUTH0_CLIENT_ID="${AUTH0_CLIENT_ID}" \
        --set app.deployment.env.AUTH0_CLIENT_SECRET="${AUTH0_CLIENT_SECRET}"

helm-uninstall:
	helm uninstall coat-mvp-dashboards --namespace coat-mvp-dashboards-dev
