# HARDWARIO CLI Tools

[![Test](https://github.com/hardwario/py-hardwario/actions/workflows/test.yaml/badge.svg)](https://github.com/hardwario/py-hardwario/actions/workflows/test.yaml)
[![Release](https://img.shields.io/github/release/hardwario/py-hardwario.svg)](https://github.com/hardwario/py-hardwario/releases)
[![PyPI](https://img.shields.io/pypi/v/hardwario.svg)](https://pypi.org/project/hardwario/)
[![License](https://img.shields.io/github/license/hardwario/py-hardwario.svg)](https://github.com/hardwario/py-hardwario/blob/main/LICENSE)
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
- Built-in MCP server so AI tools can drive the device console

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

## 🤖 MCP Server (AI Integration)

The device console can expose a built-in [Model Context Protocol](https://modelcontextprotocol.io/)
server, which lets AI tools (Claude, Cursor, etc.) drive the target: send shell
commands, read the log, flash firmware, and inspect memory and registers.

The server is off by default. Add `--mcp` to any `console` command:

```bash
hardwario chester app console --mcp
hardwario device nrf52 console --mcp
```

It listens on `127.0.0.1:8090` unless `--mcp-listen [HOST:]PORT` says otherwise.

### Claude Code Configuration

Add to your `.mcp.json`:

```json
{
    "mcpServers": {
        "hardwario-console": {
            "type": "http",
            "url": "http://127.0.0.1:8090/mcp"
        }
    }
}
```

When the server runs with `--mcp-token`, add the matching header:

```json
{
    "mcpServers": {
        "hardwario-console": {
            "type": "http",
            "url": "http://127.0.0.1:8090/mcp",
            "headers": {
                "Authorization": "Bearer <TOKEN>"
            }
        }
    }
}
```

### Authentication

The MCP server has no authentication by default and binds to `127.0.0.1`, which
is fine for local use. Since the tools can flash the device and read or write its
memory, set a token whenever the server leaves loopback (e.g.
`--mcp-listen 0.0.0.0:8090` on a shared debug box):

```bash
hardwario device nrf91 console --mcp --mcp-token "$(openssl rand -hex 16)"
```

Every request must then carry `Authorization: Bearer <TOKEN>`; anything else gets
`401 Unauthorized`. Binding off loopback without a token prints a warning. Note
the transport is plain HTTP, so on an untrusted network the token is visible on
the wire — use an SSH tunnel or a TLS reverse proxy for anything beyond a lab LAN.

### Keeping the session alive

Flashing drops the RTT link, which leaves the console dead until it is
re-attached. Pair `--mcp` with `--auto-reconnect` so the session comes back on
its own instead of the AI client having to notice and call `reconnect()`:

```bash
hardwario device nrf52 console --mcp --auto-reconnect
```

### Available MCP Tools

| Tool | Description |
|---|---|
| `send_command(command, timeout)` | Send a shell command to the device and wait for response |
| `read_terminal(lines)` | Read recent terminal output (device responses and sent commands) |
| `read_log(lines, after_cursor, pattern)` | Read log output from the device ring buffer, with optional regex filter |
| `wait_for_state(pattern, timeout, command, ...)` | Poll the log or terminal until a pattern shows up |
| `wait_for_connection(timeout, source)` | Block until the RTT link is up |
| `status()` | Session statistics (line counts, buffer usage, cursors, link state) |
| `flash(file_path, addr)` | Flash a firmware file (.hex, .bin, .elf, .srec) to the target device |
| `reconnect(address)` | Re-attach a stuck RTT session without resetting the device |
| `start()` / `stop()` | Resume / suspend the RTT readout |
| `jlink_open()` / `jlink_close()` | Attach or release the J-Link probe |
| `reset(halt)` | Reset the target; RTT re-attaches automatically (unless halting) |
| `halt()` / `go()` | Stop / resume the target CPU |
| `target_status()` | CPU halted flag and core identification |
| `read_memory(address, length, width, to_file)` | Hexdump of RAM, peripherals or memory-mapped flash |
| `write_memory(address, data, width, from_file)` | Write RAM or peripheral registers |
| `write_flash(address, data, from_file)` | Program internal flash bytes (reset+halt, program, reboot) |
| `read_registers()` | Core CPU registers (requires a halted target) |
| `memory_zones()` | Memory zones supported by the J-Link for the target |

## License

This project is licensed under the [MIT License](https://opensource.org/licenses/MIT/) - see the [LICENSE](LICENSE) file for details.

---

Made with &#x2764;&nbsp; by [**HARDWARIO a.s.**](https://www.hardwario.com/) in the heart of Europe.
