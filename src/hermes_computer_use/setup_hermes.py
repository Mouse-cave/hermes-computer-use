"""
一键接入：把 computer-use MCP 服务写进 Hermes / Claude 的配置（并装 Skills）。

安装本项目后运行：
    hermes-computer-use-setup                      # 默认接入 Hermes
    hermes-computer-use-setup --target claude-desktop
    hermes-computer-use-setup --target claude-code
    hermes-computer-use-setup --target all         # Hermes + Claude 全接
    hermes-computer-use-setup --print              # 只打印将写入的内容，不落盘(dry-run)
    hermes-computer-use-setup --hermes-dir <path>  # 手动指定 Hermes 主目录

通用做法：合并写入对应客户端的 MCP 配置（保留其余配置、原文件备份），command 用当前 Python
解释器(sys.executable)避免 PATH 问题。完成后在对应客户端重载/重启即可。
"""

from __future__ import annotations

import argparse
import json
import os
import shutil
import sys
from pathlib import Path


# ---------------------------------------------------------------------------
# 通用：MCP 服务条目（command/args/env）
# ---------------------------------------------------------------------------

# MCP 服务名（`computer-use` 在 Claude Code 里是保留名，故用带前缀的描述名）
SERVER_NAME = "hermes-computer-use"


def _base_entry() -> dict:
    return {
        "command": sys.executable,
        "args": ["-m", "hermes_computer_use.server"],
        "env": {"HCU_MAX_WIDTH": "1280", "HCU_FAILSAFE": "true"},
    }


def _drop_legacy(servers: dict) -> None:
    """清掉本脚本早期版本写入的旧名 `computer-use`（仅当它确实指向本服务）。"""
    old = servers.get("computer-use")
    if isinstance(old, dict) and any("hermes_computer_use.server" in str(a) for a in old.get("args", [])):
        servers.pop("computer-use", None)


def _repo_skills_dir() -> Path | None:
    root = Path(__file__).resolve().parents[2]  # 仓库根（editable 安装下可用）
    sk = root / "skills"
    return sk if sk.is_dir() else None


def install_skills(dest_root: Path, dry: bool) -> list[str]:
    """把仓库 skills/ 下含 SKILL.md 的技能复制到 dest_root。返回技能名列表。"""
    src = _repo_skills_dir()
    if not src:
        return []
    copied: list[str] = []
    for skill in sorted(src.iterdir()):
        if (skill / "SKILL.md").exists():
            copied.append(skill.name)
            if not dry:
                dest = dest_root / skill.name
                if dest.exists():
                    shutil.rmtree(dest)
                shutil.copytree(skill, dest)
    return copied


def _backup(path: Path) -> None:
    if path.exists():
        shutil.copy2(path, path.with_name(path.name + ".bak"))


# ---------------------------------------------------------------------------
# 目标 1：Hermes（YAML config.yaml + skills）
# ---------------------------------------------------------------------------

def _hermes_homes() -> list[Path]:
    homes: list[Path] = []
    env = os.environ.get("HERMES_CONFIG_DIR")
    if env:
        homes.append(Path(env).expanduser())
    if sys.platform == "win32" and os.environ.get("LOCALAPPDATA"):
        homes.append(Path(os.environ["LOCALAPPDATA"]) / "hermes")
    homes.append(Path.home() / ".hermes")
    out, seen = [], set()
    for h in homes:
        if h not in seen:
            seen.add(h)
            out.append(h)
    return out


def resolve_hermes_home(explicit: str | None) -> Path:
    if explicit:
        return Path(explicit).expanduser()
    cands = _hermes_homes()
    for h in cands:
        if (h / "config.yaml").exists():
            return h
    for h in cands:
        if h.exists():
            return h
    return cands[0]


def setup_hermes(explicit_dir: str | None, dry: bool) -> None:
    try:
        import yaml
    except ImportError:
        print("  ❌ 缺少 pyyaml（Hermes 用 YAML 配置），请：pip install pyyaml")
        return
    home = resolve_hermes_home(explicit_dir)
    print(f"[Hermes] 主目录：{home}")
    cfg = home / "config.yaml"
    data: dict = {}
    if cfg.exists():
        with open(cfg, "r", encoding="utf-8") as f:
            data = yaml.safe_load(f) or {}
    entry = _base_entry()
    entry.update({"enabled": True, "timeout": 120})
    data.setdefault("mcp_servers", {})
    _drop_legacy(data["mcp_servers"])
    data["mcp_servers"][SERVER_NAME] = entry
    skills = install_skills(home / "skills", dry)
    if dry:
        print(yaml.safe_dump({"mcp_servers": {SERVER_NAME: entry}},
                             allow_unicode=True, sort_keys=False))
        print(f"  将装 Skills：{skills or '(未找到 skills/)'}")
        return
    home.mkdir(parents=True, exist_ok=True)
    _backup(cfg)
    with open(cfg, "w", encoding="utf-8") as f:
        yaml.safe_dump(data, f, allow_unicode=True, sort_keys=False)
    print(f"  ✅ 配置：{cfg}（原文件已备份 .bak）")
    print(f"  ✅ Skills：{skills or '(未找到，跳过)'}")
    print("  下一步：Hermes 里 /reload-mcp")


# ---------------------------------------------------------------------------
# 目标 2：Claude Desktop（JSON）
# ---------------------------------------------------------------------------

def _claude_desktop_path() -> Path | None:
    if sys.platform == "win32":
        base = os.environ.get("APPDATA")
        return Path(base) / "Claude" / "claude_desktop_config.json" if base else None
    if sys.platform == "darwin":
        return Path.home() / "Library" / "Application Support" / "Claude" / "claude_desktop_config.json"
    return Path.home() / ".config" / "Claude" / "claude_desktop_config.json"


def setup_claude_desktop(dry: bool) -> None:
    p = _claude_desktop_path()
    print(f"[Claude Desktop] 配置：{p}")
    if not p:
        print("  ❌ 无法定位配置路径")
        return
    data: dict = {}
    if p.exists():
        try:
            data = json.loads(p.read_text(encoding="utf-8") or "{}")
        except json.JSONDecodeError:
            data = {}
    data.setdefault("mcpServers", {})
    _drop_legacy(data["mcpServers"])
    data["mcpServers"][SERVER_NAME] = _base_entry()
    if dry:
        print(json.dumps({"mcpServers": {SERVER_NAME: _base_entry()}},
                         ensure_ascii=False, indent=2))
        return
    p.parent.mkdir(parents=True, exist_ok=True)
    _backup(p)
    p.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"  ✅ 已写入（原文件已备份 .bak）")
    print("  下一步：重启 Claude Desktop")


# ---------------------------------------------------------------------------
# 目标 3：Claude Code（优先用 `claude mcp add` CLI；并装技能到 ~/.claude/skills）
# ---------------------------------------------------------------------------

def setup_claude_code(dry: bool) -> None:
    import subprocess

    claude = shutil.which("claude")
    cmd = ["claude", "mcp", "add", SERVER_NAME, "--scope", "user",
           "--env", "HCU_MAX_WIDTH=1280", "--env", "HCU_FAILSAFE=true",
           "--", sys.executable, "-m", "hermes_computer_use.server"]
    print("[Claude Code]")
    skills = install_skills(Path.home() / ".claude" / "skills", dry)
    if dry or not claude:
        if not claude:
            print("  ⚠️ 未找到 `claude` CLI，请手动执行：")
        print("  " + " ".join(cmd))
        print(f"  将装 Skills 到 ~/.claude/skills：{skills or '(未找到 skills/)'}")
        return
    try:
        # Windows 上 `claude` 多为 .cmd 包装，需经 shell 执行；其它平台直接调
        if sys.platform == "win32":
            subprocess.run(subprocess.list2cmdline(cmd), check=True, shell=True)
        else:
            subprocess.run(cmd, check=True)
        print("  ✅ 已通过 `claude mcp add` 注册")
    except Exception as exc:  # noqa: BLE001
        print(f"  ❌ `claude mcp add` 失败：{exc}\n  可手动执行：{' '.join(cmd)}")
    print(f"  ✅ Skills：{skills or '(未找到，跳过)'}")


# ---------------------------------------------------------------------------

def main() -> None:
    ap = argparse.ArgumentParser(description="一键把 computer-use MCP 接入 Hermes / Claude")
    ap.add_argument("--target", choices=["hermes", "claude-desktop", "claude-code", "all"],
                    default="hermes", help="接入目标，默认 hermes")
    ap.add_argument("--hermes-dir", default=None, help="Hermes 主目录(含 config.yaml)")
    ap.add_argument("--print", dest="dry", action="store_true", help="只打印不落盘(dry-run)")
    args = ap.parse_args()

    targets = ["hermes", "claude-desktop", "claude-code"] if args.target == "all" else [args.target]
    for t in targets:
        if t == "hermes":
            setup_hermes(args.hermes_dir, args.dry)
        elif t == "claude-desktop":
            setup_claude_desktop(args.dry)
        elif t == "claude-code":
            setup_claude_code(args.dry)
        print()


if __name__ == "__main__":
    main()
