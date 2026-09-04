.PHONY: build-GetDriversFunction

build-GetDriversFunction:
	uv export --package formula1-drivers-service --no-dev --no-emit-project --no-emit-workspace --no-hashes --locked --output-file $(ARTIFACTS_DIR)/requirements.txt
	uv pip install --python-platform aarch64-manylinux2014 --python-version 3.12 --target $(ARTIFACTS_DIR) --requirements $(ARTIFACTS_DIR)/requirements.txt
	cp -R services/drivers/src/drivers_service $(ARTIFACTS_DIR)/drivers_service
	cp -R packages/lambda-common/src/formula1_lambda_common $(ARTIFACTS_DIR)/formula1_lambda_common
	rm $(ARTIFACTS_DIR)/requirements.txt
