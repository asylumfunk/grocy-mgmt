PYTHON = python3.12
venv_name = grocy-mgmt
venv_root = $(HOME)/.local/virtualenvs
venv_path = $(venv_root)/$(venv_name)
venv_requirements = requirements.txt

.PHONY: venv
venv: $(venv_path)  ## Create and print virtualenv
	@echo '$(venv_path)'

$(venv_path):  # Create the virtualenv, if needed
	@[ -d '$(@)' ] \
	|| $(PYTHON) -m venv '$(@)' \
	>/dev/stderr

.PHONY: clean
clean:  ## Remove existing virtualenv
	deactivate 2>/dev/null || true
	rm -rf '$(venv_path)'

.PHONY: requirements $(venv_requirements)
requirements: $(venv_requirements)  ## Install python requirements
$(venv_requirements):  # Install python requirements from file
	pip install -r '$(@)'

.PHONY: main
main:  ## Run the main python code
	env \
		'GROCY_API_HOST=$(GROCY_API_HOST)' \
		'GROCY_API_PORT=$(GROCY_API_PORT)' \
		'GROCY_API_KEY=$(GROCY_API_KEY)' \
	$(PYTHON) \
		src/grocy_mgmt/main.py \
	;
