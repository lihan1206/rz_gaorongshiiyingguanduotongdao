import logging
from typing import List, Optional, TypeVar, Generic, Dict, Any
from contextlib import contextmanager
from datetime import datetime

from sqlalchemy import create_engine, text
from sqlalchemy.exc import SQLAlchemyError, OperationalError, TimeoutError
from sqlalchemy.orm import sessionmaker, Session, scoped_session
from sqlalchemy.inspection import inspect

logger = logging.getLogger(__name__)

T = TypeVar('T')


class DatabaseError(Exception):
    """Base exception for database-related errors"""
    pass


class ConnectionError(DatabaseError):
    """Exception raised for database connection errors"""
    pass


class QueryError(DatabaseError):
    """Exception raised for database query errors"""
    pass


class DatabaseManager:
    def __init__(
        self,
        database_url: str,
        pool_size: int = 5,
        max_overflow: int = 10,
        pool_recycle: int = 3600,
        pool_pre_ping: bool = True,
    ):
        self.database_url = database_url
        self.engine = None
        self.SessionLocal = None
        self._session = None
        self._create_engine(pool_size, max_overflow, pool_recycle, pool_pre_ping)

    def _create_engine(
        self,
        pool_size: int,
        max_overflow: int,
        pool_recycle: int,
        pool_pre_ping: bool,
    ) -> None:
        try:
            self.engine = create_engine(
                self.database_url,
                pool_size=pool_size,
                max_overflow=max_overflow,
                pool_recycle=pool_recycle,
                pool_pre_ping=pool_pre_ping,
                echo=False,
            )
            self.SessionLocal = sessionmaker(
                bind=self.engine,
                autoflush=False,
                autocommit=False,
                expire_on_commit=False,
            )
            logger.info("数据库引擎初始化成功")
        except SQLAlchemyError as e:
            logger.error(f"数据库引擎初始化失败: {e}")
            raise ConnectionError(f"数据库引擎初始化失败: {e}") from e

    def test_connection(self) -> bool:
        try:
            with self.engine.connect() as conn:
                conn.execute(text("SELECT 1"))
            logger.info("数据库连接测试成功")
            return True
        except OperationalError as e:
            logger.error(f"数据库连接失败: {e}")
            raise ConnectionError(f"无法连接到数据库: {e}") from e
        except SQLAlchemyError as e:
            logger.error(f"数据库测试查询失败: {e}")
            raise ConnectionError(f"数据库测试失败: {e}") from e

    @contextmanager
    def get_session(self) -> Session:
        if not self.SessionLocal:
            raise ConnectionError("数据库会话未初始化")

        session = self.SessionLocal()
        try:
            yield session
        except OperationalError as e:
            logger.error(f"数据库操作失败 (连接错误): {e}")
            session.rollback()
            raise ConnectionError(f"数据库连接错误: {e}") from e
        except TimeoutError as e:
            logger.error(f"数据库操作超时: {e}")
            session.rollback()
            raise ConnectionError(f"数据库操作超时: {e}") from e
        except SQLAlchemyError as e:
            logger.error(f"数据库操作失败: {e}")
            session.rollback()
            raise QueryError(f"数据库查询错误: {e}") from e
        except Exception as e:
            logger.error(f"未知数据库错误: {e}")
            session.rollback()
            raise DatabaseError(f"未知数据库错误: {e}") from e
        finally:
            session.close()

    def create_tables(self, base_class: Any) -> None:
        try:
            base_class.metadata.create_all(bind=self.engine)
            logger.info("数据库表创建成功")
        except SQLAlchemyError as e:
            logger.error(f"创建数据库表失败: {e}")
            raise DatabaseError(f"创建数据库表失败: {e}") from e

    def drop_tables(self, base_class: Any) -> None:
        try:
            base_class.metadata.drop_all(bind=self.engine)
            logger.info("数据库表删除成功")
        except SQLAlchemyError as e:
            logger.error(f"删除数据库表失败: {e}")
            raise DatabaseError(f"删除数据库表失败: {e}") from e


class BaseRepository(Generic[T]):
    def __init__(self, db_manager: DatabaseManager, model_class: T):
        self.db_manager = db_manager
        self.model_class = model_class
        self.model_name = model_class.__name__

    def create(self, entity: T) -> T:
        try:
            with self.db_manager.get_session() as session:
                session.add(entity)
                session.commit()
                session.refresh(entity)
                logger.debug(f"创建 {self.model_name}: {entity}")
                return entity
        except DatabaseError as e:
            logger.error(f"创建 {self.model_name} 失败: {e}")
            raise

    def bulk_create(self, entities: List[T]) -> List[T]:
        try:
            with self.db_manager.get_session() as session:
                session.bulk_save_objects(entities)
                session.commit()
                logger.debug(f"批量创建 {len(entities)} 个 {self.model_name}")
                return entities
        except DatabaseError as e:
            logger.error(f"批量创建 {self.model_name} 失败: {e}")
            raise

    def get_by_id(self, entity_id: int) -> Optional[T]:
        try:
            with self.db_manager.get_session() as session:
                return session.query(self.model_class).filter_by(id=entity_id).first()
        except DatabaseError as e:
            logger.error(f"查询 {self.model_name}(id={entity_id}) 失败: {e}")
            raise

    def update(self, entity_id: int, update_data: Dict[str, Any]) -> Optional[T]:
        try:
            with self.db_manager.get_session() as session:
                entity = session.query(self.model_class).filter_by(id=entity_id).first()
                if entity:
                    for key, value in update_data.items():
                        if hasattr(entity, key):
                            setattr(entity, key, value)
                    session.commit()
                    session.refresh(entity)
                    logger.debug(f"更新 {self.model_name}(id={entity_id})")
                return entity
        except DatabaseError as e:
            logger.error(f"更新 {self.model_name}(id={entity_id}) 失败: {e}")
            raise

    def delete(self, entity_id: int) -> bool:
        try:
            with self.db_manager.get_session() as session:
                entity = session.query(self.model_class).filter_by(id=entity_id).first()
                if entity:
                    session.delete(entity)
                    session.commit()
                    logger.debug(f"删除 {self.model_name}(id={entity_id})")
                    return True
                return False
        except DatabaseError as e:
            logger.error(f"删除 {self.model_name}(id={entity_id}) 失败: {e}")
            raise

    def list_all(self, limit: Optional[int] = None, offset: int = 0) -> List[T]:
        try:
            with self.db_manager.get_session() as session:
                query = session.query(self.model_class).order_by(self.model_class.id.desc())
                if limit:
                    query = query.limit(limit).offset(offset)
                return query.all()
        except DatabaseError as e:
            logger.error(f"查询所有 {self.model_name} 失败: {e}")
            raise

    def count(self) -> int:
        try:
            with self.db_manager.get_session() as session:
                return session.query(self.model_class).count()
        except DatabaseError as e:
            logger.error(f"统计 {self.model_name} 数量失败: {e}")
            raise

    def find_by_field(self, field_name: str, value: Any) -> List[T]:
        try:
            with self.db_manager.get_session() as session:
                return session.query(self.model_class).filter(
                    getattr(self.model_class, field_name) == value
                ).all()
        except DatabaseError as e:
            logger.error(f"按字段查询 {self.model_name} 失败: {e}")
            raise
        except AttributeError as e:
            logger.error(f"字段 {field_name} 不存在于 {self.model_name}: {e}")
            raise QueryError(f"无效字段名: {field_name}") from e


class DataRepository(BaseRepository):
    def __init__(self, db_manager: DatabaseManager, model_class):
        super().__init__(db_manager, model_class)

    def get_by_time_range(
        self,
        channel_id: Optional[int] = None,
        start_time: Optional[datetime] = None,
        end_time: Optional[datetime] = None,
        limit: Optional[int] = None,
    ) -> List:
        try:
            with self.db_manager.get_session() as session:
                query = session.query(self.model_class)
                if channel_id:
                    query = query.filter_by(channel_id=channel_id)
                if start_time:
                    query = query.filter(self.model_class.sample_time >= start_time)
                if end_time:
                    query = query.filter(self.model_class.sample_time <= end_time)
                query = query.order_by(self.model_class.sample_time.desc())
                if limit:
                    query = query.limit(limit)
                return query.all()
        except DatabaseError as e:
            logger.error(f"按时间范围查询数据失败: {e}")
            raise


class AlarmRepository(BaseRepository):
    def __init__(self, db_manager: DatabaseManager, model_class):
        super().__init__(db_manager, model_class)

    def get_active_alarms(self, channel_id: Optional[int] = None) -> List:
        try:
            with self.db_manager.get_session() as session:
                query = session.query(self.model_class).filter_by(resolved=False)
                if channel_id:
                    query = query.filter_by(channel_id=channel_id)
                return query.order_by(self.model_class.occurred_at.desc()).all()
        except DatabaseError as e:
            logger.error(f"查询活跃报警失败: {e}")
            raise

    def resolve_alarm(self, alarm_id: int, resolved_note: str = "") -> bool:
        try:
            with self.db_manager.get_session() as session:
                alarm = session.query(self.model_class).filter_by(id=alarm_id).first()
                if alarm:
                    alarm.resolved = True
                    alarm.resolved_at = datetime.utcnow()
                    alarm.resolved_note = resolved_note
                    session.commit()
                    logger.info(f"报警 {alarm_id} 已解除")
                    return True
                return False
        except DatabaseError as e:
            logger.error(f"解除报警 {alarm_id} 失败: {e}")
            raise
