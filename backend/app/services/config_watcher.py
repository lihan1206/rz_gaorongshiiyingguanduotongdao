import logging
import threading
import time
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional

from watchdog.events import FileSystemEventHandler
from watchdog.observers import Observer

from app.services.config_manager import get_config_manager

logger = logging.getLogger(__name__)


class ConfigFileHandler(FileSystemEventHandler):
    def __init__(self, config_path: Path, on_change: Callable[[], None]):
        self.config_path = config_path
        self.on_change = on_change
        self._debounce_timer: Optional[threading.Timer] = None
        self._debounce_lock = threading.Lock()

    def on_modified(self, event):
        if event.is_directory:
            return

        if Path(event.src_path).resolve() == self.config_path.resolve():
            self._debounce_callback()

    def _debounce_callback(self):
        with self._debounce_lock:
            if self._debounce_timer:
                self._debounce_timer.cancel()

            self._debounce_timer = threading.Timer(0.5, self._execute_callback)
            self._debounce_timer.start()

    def _execute_callback(self):
        try:
            logger.info("检测到配置文件变更，触发重载")
            self.on_change()
        except Exception as e:
            logger.error(f"配置重载回调执行失败: {e}")


class ConfigWatcher:
    def __init__(self, config_path: Optional[Path] = None):
        self.config_path = config_path or Path(__file__).parent.parent / "core" / "config.json"
        self.config_manager = get_config_manager()
        self._observer: Optional[Observer] = None
        self._callbacks: List[Callable[[Dict[str, Any]], None]] = []
        self._running = False

    def start(self) -> None:
        if self._running:
            logger.warning("配置监听器已在运行")
            return

        if not self.config_path.exists():
            logger.warning(f"配置文件不存在: {self.config_path}")
            return

        event_handler = ConfigFileHandler(
            self.config_path,
            self._on_config_changed,
        )

        self._observer = Observer()
        self._observer.schedule(
            event_handler,
            str(self.config_path.parent),
            recursive=False,
        )
        self._observer.start()
        self._running = True
        logger.info(f"配置文件监听已启动: {self.config_path}")

    def stop(self) -> None:
        if self._observer:
            self._observer.stop()
            self._observer.join(timeout=5.0)
            self._observer = None
        self._running = False
        logger.info("配置文件监听已停止")

    def _on_config_changed(self) -> None:
        if self.config_manager.reload_if_changed():
            config = self.config_manager.get_all()
            self._notify_callbacks(config)

    def register_callback(self, callback: Callable[[Dict[str, Any]], None]) -> None:
        self._callbacks.append(callback)
        self.config_manager.register_callback(callback)

    def unregister_callback(self, callback: Callable[[Dict[str, Any]], None]) -> None:
        if callback in self._callbacks:
            self._callbacks.remove(callback)
        self.config_manager.unregister_callback(callback)

    def _notify_callbacks(self, config: Dict[str, Any]) -> None:
        for callback in self._callbacks:
            try:
                callback(config)
            except Exception as e:
                logger.error(f"配置变更回调执行失败: {e}")

    @property
    def is_running(self) -> bool:
        return self._running


_config_watcher: Optional[ConfigWatcher] = None


def get_config_watcher() -> ConfigWatcher:
    global _config_watcher
    if _config_watcher is None:
        _config_watcher = ConfigWatcher()
    return _config_watcher


def start_config_watcher() -> ConfigWatcher:
    watcher = get_config_watcher()
    watcher.start()
    return watcher


def stop_config_watcher() -> None:
    global _config_watcher
    if _config_watcher:
        _config_watcher.stop()
