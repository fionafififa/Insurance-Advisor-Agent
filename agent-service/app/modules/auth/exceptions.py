from app.core.exceptions import ApplicationError


class InvalidCredentialsError(ApplicationError):
    status_code = 400
    code = "INVALID_CREDENTIALS"
    message = "用户名/邮箱或密码错误"


class UnauthorizedError(ApplicationError):
    status_code = 401
    code = "UNAUTHORIZED"
    message = "登录凭证无效或已过期"
    headers = {"WWW-Authenticate": "Bearer"}
