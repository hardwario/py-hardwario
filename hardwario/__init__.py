from importlib.metadata import PackageNotFoundError, version

try:
    __version__ = version('hardwario')
except PackageNotFoundError:  # not installed, e.g. a bare source checkout
    __version__ = '0.0.0.dev0'
