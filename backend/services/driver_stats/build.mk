.PHONY: build-GetDriverStatsFunction

build-GetDriverStatsFunction:
	uv export --package formula1-driver-stats-service --no-dev --no-emit-project --no-emit-workspace --no-hashes --locked --output-file $(ARTIFACTS_DIR)/requirements.txt
	uv pip install --python-platform aarch64-manylinux_2_34 --python-version 3.12 --only-binary :all: --target $(ARTIFACTS_DIR) --requirements $(ARTIFACTS_DIR)/requirements.txt
	cp -R services/driver_stats/src/driver_stats_service $(ARTIFACTS_DIR)/driver_stats_service
	cp -R packages/lambda-common/src/formula1_lambda_common $(ARTIFACTS_DIR)/formula1_lambda_common
	rm $(ARTIFACTS_DIR)/requirements.txt

