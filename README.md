# spacehaven-cheat-engine

A new project created from git-repokit-template

## Installation

```bash
pip install spacehaven_cheat_engine
```

### From Source

```bash
git clone https://github.com/djdarcy/spacehaven-cheat-engine.git
cd spacehaven-cheat-engine
pip install -e ".[dev]"
```

## Usage

```bash
spacehaven-cheat-engine --help
```

## Development

```bash
# Clone and install
git clone https://github.com/djdarcy/spacehaven-cheat-engine.git
cd spacehaven-cheat-engine
python -m venv .venv
source .venv/bin/activate  # or .venv\Scripts\activate on Windows
pip install -e ".[dev]"

# Run tests
python -m pytest tests/ -v

# Install git hooks (if using repokit-common submodule)
bash scripts/repokit-common/install-hooks.sh
```

## License

GPL-3.0-or-later. See [LICENSE](LICENSE) for details.

