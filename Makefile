UV = uv --directory services/api
.PHONY: setup api web db db-stop db-native db-native-stop migrate check smoke
setup:
	npm ci
	$(UV) sync --locked
api:
	$(UV) run --locked uvicorn maxx.main:app --reload --host 127.0.0.1 --port 8000
web:
	npm run dev:web
db:
	docker compose up -d --wait postgres
db-stop:
	docker compose stop postgres
db-native:
	bash scripts/postgres-local.sh start
db-native-stop:
	bash scripts/postgres-local.sh stop
migrate:
	$(UV) run --locked alembic upgrade head
check:
	npm run lint
	npm run typecheck
	npm run test --workspace @maxx/web
	npm run build
	$(UV) run --locked ruff check .
	$(UV) run --locked ruff format --check .
	$(UV) run --locked pytest
smoke:
	npm run smoke

.PHONY: evaluate evaluate-live
evaluate:
	$(UV) run --locked python -m maxx.evaluate --mode fixture
evaluate-live:
	$(UV) run --locked python -m maxx.evaluate --mode live

.PHONY: verify-persistence migrate-legacy
verify-persistence:
	$(UV) run --locked python -m maxx.verify_persistence
migrate-legacy:
	$(UV) run --locked python -m maxx.migrate_legacy
