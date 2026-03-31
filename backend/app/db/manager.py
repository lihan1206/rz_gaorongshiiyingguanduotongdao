import logging
from contextlib import contextmanager
from typing import Generator, Optional

from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session

from app.db.session import SessionLocal

logger = logging.getLogger(__name__)


class DatabaseError(Exception):
    """数据库操作异常"""
    pass


class DatabaseConnectionError(DatabaseError):
    """数据库连接异常"""
    pass


class DatabaseManager:
    """数据库管理器 - 负责数据库连接和操作"""

    def __init__(self):
        self._session_factory = SessionLocal

    @contextmanager
    def get_session(self) -> Generator[Session, None, None]:
        """获取数据库会话上下文管理器"""
        session = self._session_factory()
        try:
            yield session
            session.commit()
        except SQLAlchemyError as e:
            session.rollback()
            logger.error(f"数据库操作失败: {e}")
            raise DatabaseError(f"数据库操作失败: {e}") from e
        except Exception as e:
            session.rollback()
            logger.error(f"未知错误: {e}")
            raise
        finally:
            session.close()

    def test_connection(self) -> bool:
        """测试数据库连接"""
        try:
            with self.get_session() as session:
                session.execute("SELECT 1")
                return True
        except Exception as e:
            logger.error(f"数据库连接测试失败: {e}")
            return False

    def execute_with_retry(self, operation, max_retries: int = 3):
        """带重试的数据库操作"""
        last_error = None
        for attempt in range(max_retries):
            try:
                with self.get_session() as session:
                    return operation(session)
            except DatabaseConnectionError as e:
                last_error = e
                logger.warning(f"数据库操作失败，尝试重试 ({attempt + 1}/{max_retries}): {e}")
        raise last_error


# 全局数据库管理器实例
db_manager = DatabaseManager()


def get_db_session() -> Generator[Session, None, None]:
    """FastAPI依赖注入使用的数据库会话生成器"""
    session = SessionLocal()
    try:
        yield session
        session.commit()
    except SQLAlchemyError as e:
        session.rollback()
        logger.error(f"数据库操作失败: {e}")
        raise DatabaseError(f"数据库操作失败: {e}") from e
    except Exception as e:
        session.rollback()
        logger.error(f"未知错误: {e}")
        raise
    finally:
        session.close()
