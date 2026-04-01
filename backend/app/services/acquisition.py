import asyncio
import logging
from datetime import datetime
from typing import Dict, List, Optional, Any
from concurrent.futures import ProcessPoolExecutor, ThreadPoolExecutor
from dataclasses import dataclass

from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.interval import IntervalTrigger

from app.sensor import SensorManager, SensorData
from app.fusion import FusionManager
from app.database import DatabaseManager
from app.config import AppConfig

logger = logging.getLogger(__name__)


@dataclass
class AcquisitionResult:
    """采集结果"""
    channel_id: int
    success: bool
    data: Optional[SensorData] = None
    error: Optional[str] = None
    timestamp: Optional[datetime] = None


class AsyncDataAcquisition:
    """异步数据采集器 - 使用线程池处理IO密集型任务"""

    def __init__(
        self,
        sensor_manager: SensorManager,
        fusion_manager: FusionManager,
        db_manager: DatabaseManager,
        max_workers: int = 8,
    ):
        self.sensor_manager = sensor_manager
        self.fusion_manager = fusion_manager
        self.db_manager = db_manager
        self._executor = ThreadPoolExecutor(max_workers=max_workers)
        self._running: bool = False
        self._tasks: List[asyncio.Task] = []

    async def _read_single_channel(
        self,
        channel_id: int,
        temperature: Optional[float] = None,
    ) -> AcquisitionResult:
        """读取单个通道数据"""
        try:
            loop = asyncio.get_running_loop()
            sensor_data = await loop.run_in_executor(
                self._executor,
                self.sensor_manager.read_channel,
                channel_id,
                temperature,
            )
            
            fused_data = self.fusion_manager.process_sensor_data(sensor_data)
            
            return AcquisitionResult(
                channel_id=channel_id,
                success=True,
                data=fused_data,
                timestamp=datetime.utcnow(),
            )
        except Exception as e:
            error_msg = f"通道 {channel_id} 采集失败: {str(e)}"
            logger.error(error_msg)
            return AcquisitionResult(
                channel_id=channel_id,
                success=False,
                error=error_msg,
                timestamp=datetime.utcnow(),
            )

    async def read_all_channels(
        self,
        temperature: Optional[float] = None,
    ) -> List[AcquisitionResult]:
        """并行读取所有通道"""
        tasks = []
        for channel_id in self.sensor_manager.simulators.keys():
            task = asyncio.create_task(
                self._read_single_channel(channel_id, temperature)
            )
            tasks.append(task)

        results = await asyncio.gather(*tasks, return_exceptions=True)
        
        processed_results = []
        for result in results:
            if isinstance(result, Exception):
                logger.error(f"采集任务失败: {result}")
            else:
                processed_results.append(result)
        
        return processed_results

    async def start_continuous_acquisition(
        self,
        interval_ms: int = 100,
        temperature: Optional[float] = None,
    ) -> None:
        """启动连续采集"""
        self._running = True
        logger.info(f"启动连续数据采集，间隔: {interval_ms}ms")

        while self._running:
            try:
                start_time = asyncio.get_event_loop().time()
                
                results = await self.read_all_channels(temperature)
                
                success_count = sum(1 for r in results if r.success)
                logger.debug(f"采集完成: 成功 {success_count}/{len(results)} 通道")
                
                elapsed = asyncio.get_event_loop().time() - start_time
                sleep_time = max(0, interval_ms / 1000 - elapsed)
                await asyncio.sleep(sleep_time)
                
            except Exception as e:
                logger.error(f"连续采集循环错误: {e}")
                await asyncio.sleep(1)

    def stop(self) -> None:
        """停止采集"""
        self._running = False
        self._executor.shutdown(wait=True)
        logger.info("数据采集已停止")


class ProcessDataAcquisition:
    """多进程数据采集器 - 使用进程池处理CPU密集型任务"""

    def __init__(
        self,
        num_channels: int = 8,
        max_workers: int = 4,
    ):
        self.num_channels = num_channels
        self._executor = ProcessPoolExecutor(max_workers=max_workers)

    @staticmethod
    def _worker_process(
        channel_id: int,
        base_value: float,
        noise_level: float,
    ) -> Dict[str, Any]:
        """工作进程 - 模拟传感器数据采集"""
        import random
        from datetime import datetime

        noise = random.uniform(-noise_level, noise_level)
        value = max(0.0, min(100.0, base_value + noise))
        
        return {
            "channel_id": channel_id,
            "capacitive_value": round(value, 3),
            "ultrasonic_value": round(value + random.uniform(-1, 1), 3),
            "timestamp": datetime.utcnow().isoformat(),
        }

    async def read_all_channels(
        self,
        base_values: Optional[Dict[int, float]] = None,
    ) -> List[Dict[str, Any]]:
        """多进程并行采集"""
        if base_values is None:
            base_values = {i: 50.0 for i in range(1, self.num_channels + 1)}

        loop = asyncio.get_running_loop()
        tasks = []
        
        for channel_id, base_value in base_values.items():
            task = loop.run_in_executor(
                self._executor,
                self._worker_process,
                channel_id,
                base_value,
                2.0,
            )
            tasks.append(task)

        results = await asyncio.gather(*tasks, return_exceptions=True)
        
        processed = []
        for result in results:
            if isinstance(result, Exception):
                logger.error(f"进程采集失败: {result}")
            else:
                processed.append(result)
        
        return processed

    def shutdown(self) -> None:
        """关闭进程池"""
        self._executor.shutdown(wait=True)


class ScheduledAcquisitionService:
    """定时采集服务"""

    def __init__(
        self,
        sensor_manager: SensorManager,
        fusion_manager: FusionManager,
        db_manager: DatabaseManager,
    ):
        self.sensor_manager = sensor_manager
        self.fusion_manager = fusion_manager
        self.db_manager = db_manager
        self._scheduler: Optional[AsyncIOScheduler] = None
        self._async_acquisition = AsyncDataAcquisition(
            sensor_manager, fusion_manager, db_manager
        )

    async def _acquisition_job(self) -> None:
        """定时采集任务"""
        try:
            results = await self._async_acquisition.read_all_channels()
            
            success_results = [r for r in results if r.success and r.data]
            if success_results:
                sensor_data_list = [r.data for r in success_results]
                
                from app.services.sampling import ingest_fused_sensor_data
                with self.db_manager.get_session() as db:
                    ingest_fused_sensor_data(db, sensor_data_list)
                
                logger.debug(f"定时采集: 保存 {len(sensor_data_list)} 条数据")
        
        except Exception as e:
            logger.error(f"定时采集任务失败: {e}")

    def start(
        self,
        interval_ms: Optional[int] = None,
        run_once: bool = False,
    ) -> None:
        """启动定时采集服务"""
        if interval_ms is None:
            sampling_settings = AppConfig.get_sampling_settings()
            interval_ms = sampling_settings.get("frequency_ms", 100)

        if run_once:
            asyncio.create_task(self._acquisition_job())
            return

        self._scheduler = AsyncIOScheduler()
        self._scheduler.add_job(
            self._acquisition_job,
            trigger=IntervalTrigger(
                seconds=interval_ms / 1000,
                jitter=0.1,
            ),
            id="data_acquisition",
            replace_existing=True,
        )
        self._scheduler.start()
        logger.info(f"定时采集服务已启动，间隔: {interval_ms}ms")

    def stop(self) -> None:
        """停止定时采集服务"""
        if self._scheduler and self._scheduler.running:
            self._scheduler.shutdown()
            logger.info("定时采集服务已停止")
        
        self._async_acquisition.stop()

    def is_running(self) -> bool:
        """检查是否正在运行"""
        return self._scheduler is not None and self._scheduler.running
