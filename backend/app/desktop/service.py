"""Anonymous stdin/stdout protocol. No business import before profile installation."""
import asyncio
import json
from pathlib import Path
import socket
import sys
import threading
from typing import TextIO

from app.desktop.profile import DesktopProfile, install_profile


def serve_from_parent_streams(reader: TextIO, writer: TextIO) -> int:
    def emit(frame):
        writer.write(json.dumps(frame, ensure_ascii=True) + "\n")
        writer.flush()
    try:
        frame = json.loads(reader.readline(65536))
        if frame.get("schemaVersion") != 1 or frame.get("type") != "start":
            raise ValueError()
        data_dir, static_dir = Path(frame["dataDir"]), Path(frame["staticDir"])
        if not data_dir.is_absolute() or not static_dir.is_absolute() or not (static_dir / "index.html").is_file():
            raise ValueError()
        token = frame["token"]
        if not isinstance(token, str) or len(token) < 32 or not token.isascii():
            raise ValueError()
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as listener:
            listener.bind(("127.0.0.1", 0))
            listener.listen(128)
            origin = f"http://127.0.0.1:{listener.getsockname()[1]}"
            profile = DesktopProfile(data_dir.resolve(), origin, token)
            install_profile(profile)
            from app.desktop.security import create_desktop_app, mount_desktop_static
            import uvicorn
            app = create_desktop_app(profile)
            mount_desktop_static(app, static_dir)
            config = uvicorn.Config(app, host="127.0.0.1", log_level="critical", access_log=False,
                                    log_config=None, timeout_graceful_shutdown=4)
            server = uvicorn.Server(config)

            async def run():
                loop = asyncio.get_running_loop()
                commands = asyncio.Queue()
                def controls():
                    try:
                        for line in reader:
                            if len(line) > 65536:
                                break
                            try:
                                item = json.loads(line)
                            except ValueError:
                                break
                            loop.call_soon_threadsafe(commands.put_nowait, item)
                    except (OSError, ValueError):
                        pass
                    finally:
                        try:
                            loop.call_soon_threadsafe(commands.put_nowait, {"type": "shutdown"})
                        except RuntimeError:
                            pass
                threading.Thread(target=controls, daemon=True, name="desktop-control").start()
                serving = asyncio.create_task(server.serve(sockets=[listener]))
                while not server.started:
                    if serving.done():
                        await serving
                        raise RuntimeError("startup failed")
                    await asyncio.sleep(0.01)
                identity = app.state.workspace
                context = dict(schemaVersion=1, mode="desktop", apiBaseUrl=origin + "/api/v1",
                               version="0.2.0-dev", workspace=dict(id=identity.workspace_id,
                               ownerId=identity.owner_id, label=identity.label))
                emit(dict(type="ready", schemaVersion=1, origin=origin, context=context))
                from app.services.import_dispatch import active_import_count, shutdown_local_imports
                while not serving.done():
                    try:
                        command = await asyncio.wait_for(commands.get(), timeout=0.1)
                    except asyncio.TimeoutError:
                        continue
                    kind, rid = command.get("type"), command.get("request_id")
                    if kind == "status":
                        emit(dict(type="status", request_id=rid, active_imports=active_import_count()))
                    elif kind == "shutdown":
                        shutdown_local_imports(wait=False, seal=True)
                        emit(dict(type="shutdown", request_id=rid))
                        server.should_exit = True
                        break
                await serving
            asyncio.run(run())
        return 0
    except Exception:
        # No traceback, paths, token or document content in protocol/diagnostics.
        emit(dict(type="error", message="本地服务启动失败，请检查数据目录和软件界面文件"))
        return 1


if __name__ == "__main__":
    raise SystemExit(serve_from_parent_streams(sys.stdin, sys.stdout))
