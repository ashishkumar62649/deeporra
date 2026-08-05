.PHONY: install dev test lint clean

install:
	pip install -e .

dev:
	pip install -e ".[dev]"

test:
	python -m pytest tests/ -v

test-cov:
	python -m pytest tests/ --cov=deeporra --cov-report=term-missing

lint:
	python -m flake8 deeporra/ tests/
	python -m mypy deeporra/ --ignore-missing-imports

clean:
	python -c "import os,shutil,glob; dirs=[*glob.glob('**/__pycache__',recursive=True),'.pytest_cache','htmlcov','build','dist','deeporra_data',*glob.glob('*.egg-info')]; [shutil.rmtree(p,ignore_errors=True) for p in dirs if os.path.isdir(p)]; [os.remove(p) for p in ('.coverage',) if os.path.exists(p)]"
