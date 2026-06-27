"""
Mnemosyne v5.0 — 统一响应格式
白皮书 §13.1.2 全局响应结构

所有 API 返回:
{
    "code": 0,           # 0=成功, 非0=失败
    "message": "success",
    "data": {...},       # 业务数据
    "request_id": "req_xxx"  # 请求唯一标识
}
"""
import uuid
from fastapi.responses import JSONResponse


def success(data, message: str = "success", code: int = 0) -> JSONResponse:
    """成功响应"""
    return JSONResponse({
        "code": code,
        "message": message,
        "data": data,
        "request_id": f"req_{uuid.uuid4().hex[:12]}",
    })


def error(message: str, code: int = 50001, status_code: int = 500) -> JSONResponse:
    """错误响应"""
    return JSONResponse(
        status_code=status_code,
        content={
            "code": code,
            "message": message,
            "data": None,
            "request_id": f"req_{uuid.uuid4().hex[:12]}",
        }
    )


# 错误码 (白皮书 §13.1.3)
ERROR_CODES = {
    0: "成功",
    40001: "参数错误",
    40101: "鉴权失败",
    40301: "配额超限",
    40401: "资源不存在",
    40901: "版本冲突",
    50001: "服务内部错误",
    50301: "服务降级",
}
