import logging
import time
from contextlib import contextmanager
from functools import wraps
from typing import Any, Callable, List, Optional, TypeVar

from sqlalchemy.exc import (
    DatabaseError,
    IntegrityError,
    OperationalError,
    SQLAlchemyError,
)
from sqlalchemy.orm import Session

logger = logging.getLogger(__name__)

T = TypeVar("T")


class DatabaseError(Exception):
    pass


class ConnectionError(DatabaseError):
    pass


class QueryError(DatabaseError):
    pass


class RetryExhaustedError(DatabaseError):
    pass


def retry_on_error(
    max_retries: int = 3,
    retry_delay: float = 1.0,
    exponential_backoff: bool = True,
    exceptions: tuple = (OperationalError, ConnectionError),
):
    def decorator(func: Callable[..., T]) -> Callable[..., T]:
        @wraps(func)
        def wrapper(*args, **kwargs) -> T:
            last_exception = None
            delay = retry_delay

            for attempt in range(max_retries):
                try:
                    return func(*args, **kwargs)
                except exceptions as e:
                    last_exception = e
                    if attempt < max_retries - 1:
                        logger.warning(
                            f"数据库操作失败 (尝试 {attempt + 1}/{max_retries}): {e}"
                        )
                        time.sleep(delay)
                        if exponential_backoff:
                            delay *= 2
                    else:
                        logger.error(
                            f"数据库操作失败，已达到最大重试次数: {e}"
                        )

            raise RetryExhaustedError(
                f"操作失败，已重试 {max_retries} 次"
            ) from last_exception

        return wrapper

    return decorator


class DatabaseManager:
    def __init__(
        self,
        session_local,
        max_retries: int = 3,
        retry_delay: float = 1.0,
    ):
        self.SessionLocal = session_local
        self.max_retries = max_retries
        self.retry_delay = retry_delay
        self._connection_healthy = True

    @contextmanager
    def get_session(self, auto_commit: bool = True):
        session = self.SessionLocal()
        try:
            yield session
            if auto_commit:
                session.commit()
        except IntegrityError as e:
            session.rollback()
            logger.error(f"数据完整性错误: {e}")
            raise QueryError(f"数据完整性错误: {e}") from e
        except OperationalError as e:
            session.rollback()
            self._connection_healthy = False
            logger.error(f"数据库连接错误: {e}")
            raise ConnectionError(f"数据库连接错误: {e}") from e
        except DatabaseError as e:
            session.rollback()
            logger.error(f"数据库错误: {e}")
            raise
        except SQLAlchemyError as e:
            session.rollback()
            logger.error(f"SQLAlchemy错误: {e}")
            raise QueryError(f"数据库操作错误: {e}") from e
        except Exception as e:
            session.rollback()
            logger.error(f"未知数据库错误: {e}")
            raise
        finally:
            session.close()

    def check_connection(self) -> bool:
        try:
            with self.get_session() as session:
                session.execute("SELECT 1")
            self._connection_healthy = True
            return True
        except Exception as e:
            self._connection_healthy = False
            logger.error(f"数据库连接检查失败: {e}")
            return False

    @property
    def is_healthy(self) -> bool:
        return self._connection_healthy

    @retry_on_error(max_retries=3, retry_delay=1.0)
    def execute_with_retry(
        self,
        operation: Callable[[Session], T],
        auto_commit: bool = True,
    ) -> T:
        with self.get_session(auto_commit=auto_commit) as session:
            return operation(session)

    def safe_add(self, session: Session, obj: Any) -> bool:
        try:
            session.add(obj)
            return True
        except Exception as e:
            logger.error(f"添加对象失败: {e}")
            return False

    def safe_add_all(self, session: Session, objects: List[Any]) -> bool:
        try:
            session.add_all(objects)
            return True
        except Exception as e:
            logger.error(f"批量添加对象失败: {e}")
            return False

    def safe_query(
        self,
        session: Session,
        model,
        filter_condition=None,
    ) -> Optional[List[Any]]:
        try:
            query = session.query(model)
            if filter_condition is not None:
                query = query.filter(filter_condition)
            return query.all()
        except Exception as e:
            logger.error(f"查询失败: {e}")
            return None

    def safe_get(self, session: Session, model, id: int) -> Optional[Any]:
        try:
            return session.query(model).filter(model.id == id).first()
        except Exception as e:
            logger.error(f"获取记录失败 (id={id}): {e}")
            return None

    def safe_delete(self, session: Session, obj: Any) -> bool:
        try:
            session.delete(obj)
            return True
        except Exception as e:
            logger.error(f"删除对象失败: {e}")
            return False


class ChannelRepository:
    def __init__(self, db_manager: DatabaseManager):
        self.db_manager = db_manager

    def get_by_id(self, channel_id: int):
        from app.models.channel import Channel

        def operation(session: Session):
            return session.query(Channel).filter(Channel.id == channel_id).first()

        return self.db_manager.execute_with_retry(operation)

    def get_all(self):
        from app.models.channel import Channel

        def operation(session: Session):
            return session.query(Channel).all()

        return self.db_manager.execute_with_retry(operation)

    def get_by_ids(self, channel_ids: List[int]):
        from app.models.channel import Channel

        def operation(session: Session):
            return session.query(Channel).filter(Channel.id.in_(channel_ids)).all()

        return self.db_manager.execute_with_retry(operation)


class LiquidLevelDataRepository:
    def __init__(self, db_manager: DatabaseManager):
        self.db_manager = db_manager

    def create(self, data):
        def operation(session: Session):
            session.add(data)
            session.flush()
            session.refresh(data)
            return data

        return self.db_manager.execute_with_retry(operation)

    def create_batch(self, data_list):
        def operation(session: Session):
            session.add_all(data_list)
            session.flush()
            for data in data_list:
                session.refresh(data)
            return data_list

        return self.db_manager.execute_with_retry(operation)

    def get_by_channel(
        self,
        channel_id: int,
        limit: int = 100,
        offset: int = 0,
    ):
        from app.models.liquid_level_data import LiquidLevelData

        def operation(session: Session):
            return (
                session.query(LiquidLevelData)
                .filter(LiquidLevelData.channel_id == channel_id)
                .order_by(LiquidLevelData.sample_time.desc())
                .limit(limit)
                .offset(offset)
                .all()
            )

        return self.db_manager.execute_with_retry(operation)


class AlarmRepository:
    def __init__(self, db_manager: DatabaseManager):
        self.db_manager = db_manager

    def create(self, alarm):
        def operation(session: Session):
            session.add(alarm)
            session.flush()
            session.refresh(alarm)
            return alarm

        return self.db_manager.execute_with_retry(operation)

    def get_unresolved(self, channel_id: Optional[int] = None):
        from app.models.alarm import Alarm

        def operation(session: Session):
            query = session.query(Alarm).filter(Alarm.resolved == False)
            if channel_id is not None:
                query = query.filter(Alarm.channel_id == channel_id)
            return query.order_by(Alarm.occurred_at.desc()).all()

        return self.db_manager.execute_with_retry(operation)

    def resolve(self, alarm_id: int):
        from datetime import datetime

        from app.models.alarm import Alarm

        def operation(session: Session):
            alarm = session.query(Alarm).filter(Alarm.id == alarm_id).first()
            if alarm:
                alarm.resolved = True
                alarm.resolved_at = datetime.utcnow()
                return True
            return False

        return self.db_manager.execute_with_retry(operation)
