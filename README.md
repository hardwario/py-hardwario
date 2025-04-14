# HARDWARIO CLI Tools

[![Main](https://github.com/hardwario/py-hardwario/actions/workflows/main.yaml/badge.svg)](https://github.com/hardwario/py-hardwario/actions/workflows/main.yaml)
[![Release](https://img.shields.io/github/release/hardwario/py-hardwario.svg)](https://github.com/hardwario/py-hardwario/releases)
[![PyPI](https://img.shields.io/pypi/v/hardwario.svg)](https://pypi.org/project/hardwario/)
[![License](https://img.shields.io/github/license/hardwario/py-hardwario.svg)](https://github.com/hardwario/py-hardwario/blob/master/LICENSE)
[![Twitter](https://img.shields.io/twitter/follow/hardwario_en.svg?style=social&label=Follow)](https://twitter.com/hardwario_en)

**Hardwario CLI** is a command-line tool for developing, managing, and debugging devices in the [HARDWARIO ecosystem](https://www.hardwario.com/).
It supports workflows for CHESTER modules, Nordic SoCs (nRF5x, nRF91, etc.), firmware management, logging, and more.

---

## ✨ Features

- Manage CHESTER-specific application SoC features
- Open interactive device console for logs and shell access
- Flash, erase, and reset firmware for supported SoCs
- Work with HARDWARIO's Product Information Block (PIB)
- Support for multiple chip families (nRF51, nRF52, nRF91, etc.)
- Integration with SEGGER J-Link (serial number, speed control)

## 🛠️ Installation

```bash
pip install hardwario
```

## 🚀 Quick Start

```bash
hardwario --help
```

```bash
Usage: hardwario [OPTIONS] COMMAND [ARGS]...

  HARDWARIO Command Line Tool.

Options:
  --log-level [debug|info|success|warning|error|critical]
                                  Log level to stderr  [default: critical]
  --version                       Show the version and exit.
  --help                          Show this message and exit.

Commands:
  chester  Commands for CHESTER (configurable IoT gateway).
  device   Commands for devices.

```

## License

This project is licensed under the [MIT License](https://opensource.org/licenses/MIT/) - see the [LICENSE](LICENSE) file for details.

---

Made with &#x2764;&nbsp; by [**HARDWARIO a.s.**](https://www.hardwario.com/) in the heart of Europe.
