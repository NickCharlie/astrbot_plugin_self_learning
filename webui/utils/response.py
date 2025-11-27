"""
统一响应格式
"""
from quart import jsonify
from typing import Any, Optional


def success_response(data: Any = None, message: str = "成功"):
    """
    成功响应

    Args:
        data: 响应数据
        message: 响应消息

    Returns:
        JSON 响应和状态码
    """
    response = {
        'success': True,
        'message': message
    }
    if data is not None:
        response['data'] = data

    return jsonify(response), 200


def error_response(message: str = "失败", status_code: int = 400, data: Any = None):
    """
    错误响应

    Args:
        message: 错误消息
        status_code: HTTP 状态码
        data: 额外数据

    Returns:
        JSON 响应和状态码
    """
    response = {
        'success': False,
        'message': message
    }
    if data is not None:
        response['data'] = data

    return jsonify(response), status_code


def paginated_response(items: list, total: int, page: int = 1, page_size: int = 20):
    """
    分页响应

    Args:
        items: 当前页数据
        total: 总数
        page: 当前页码
        page_size: 每页数量

    Returns:
        JSON 响应
    """
    return success_response({
        'items': items,
        'pagination': {
            'total': total,
            'page': page,
            'page_size': page_size,
            'total_pages': (total + page_size - 1) // page_size
        }
    })
