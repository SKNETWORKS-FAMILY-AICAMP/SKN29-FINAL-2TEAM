"""임의 코드 실행 없이 수식·단위·날짜를 계산한다."""

from __future__ import annotations

import ast
import math
import re
from datetime import date, datetime, time, timedelta
from typing import Any
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

import dateparser
import holidays
import pint
import sympy

from services.builtin_tools.common.errors import BuiltinToolError

_MAX_EXPRESSION_LENGTH = 500
_MAX_AST_NODES = 100


def _tidy(value: float) -> float:
    """부동소수 잡음을 없앤다 — `76.99999999999993` → `77.0`, `6.213711922` 는 유지.

    유효숫자 12자리로 반올림한 뒤, 정수에 아주 가까우면 정수로 스냅한다.
    """

    if not math.isfinite(value):
        return value
    rounded = float(f"{value:.12g}")
    nearest_int = round(rounded)
    if abs(rounded - nearest_int) < 1e-9:
        return float(nearest_int)
    return rounded
_MAX_ABS_EXPONENT = 100
_BINARY_OPERATORS = {
    ast.Add: lambda left, right: left + right,
    ast.Sub: lambda left, right: left - right,
    ast.Mult: lambda left, right: left * right,
    ast.Div: lambda left, right: left / right,
    ast.Mod: lambda left, right: left % right,
    ast.Pow: lambda left, right: left**right,
}
_UNARY_OPERATORS = {ast.UAdd: lambda value: value, ast.USub: lambda value: -value}
_FUNCTIONS = {
    "abs": sympy.Abs,
    "sqrt": sympy.sqrt,
    "sin": sympy.sin,
    "cos": sympy.cos,
    "tan": sympy.tan,
    "log": sympy.log,
    "percent": lambda value: value / 100,
}
_CONSTANTS = {"pi": sympy.pi, "e": sympy.E}
_KOREAN_WEEKDAYS = {"월": 0, "화": 1, "수": 2, "목": 3, "금": 4, "토": 5, "일": 6}
_UNIT_REGISTRY = pint.UnitRegistry(autoconvert_offset_to_baseunit=True)


def _safe_expression(expression: str) -> sympy.Expr:
    if not expression or len(expression) > _MAX_EXPRESSION_LENGTH:
        raise BuiltinToolError("INVALID_EXPRESSION", "계산식은 1~500자로 입력해 주세요.")
    try:
        tree = ast.parse(expression, mode="eval")
    except SyntaxError as exc:
        raise BuiltinToolError("INVALID_EXPRESSION", "계산식을 해석하지 못했습니다.") from exc
    if sum(1 for _ in ast.walk(tree)) > _MAX_AST_NODES:
        raise BuiltinToolError("EXPRESSION_TOO_COMPLEX", "계산식이 너무 복잡합니다.")

    def evaluate(node: ast.AST) -> sympy.Expr:
        if isinstance(node, ast.Expression):
            return evaluate(node.body)
        if isinstance(node, ast.Constant) and isinstance(node.value, (int, float)):
            if isinstance(node.value, bool) or not math.isfinite(float(node.value)):
                raise BuiltinToolError("INVALID_NUMBER", "유한한 숫자만 계산할 수 있습니다.")
            return sympy.Integer(node.value) if isinstance(node.value, int) else sympy.Float(node.value)
        if isinstance(node, ast.Name) and node.id in _CONSTANTS:
            return _CONSTANTS[node.id]
        if isinstance(node, ast.BinOp) and type(node.op) in _BINARY_OPERATORS:
            left = evaluate(node.left)
            right = evaluate(node.right)
            if isinstance(node.op, ast.Pow):
                try:
                    if abs(float(right)) > _MAX_ABS_EXPONENT:
                        raise BuiltinToolError("EXPONENT_TOO_LARGE", "지수의 절댓값은 100 이하여야 합니다.")
                except (TypeError, ValueError) as exc:
                    raise BuiltinToolError("INVALID_EXPONENT", "지수는 숫자여야 합니다.") from exc
            try:
                return _BINARY_OPERATORS[type(node.op)](left, right)
            except (ZeroDivisionError, TypeError, ValueError) as exc:
                raise BuiltinToolError("CALCULATION_FAILED", "계산을 완료하지 못했습니다.") from exc
        if isinstance(node, ast.UnaryOp) and type(node.op) in _UNARY_OPERATORS:
            return _UNARY_OPERATORS[type(node.op)](evaluate(node.operand))
        if (
            isinstance(node, ast.Call)
            and isinstance(node.func, ast.Name)
            and node.func.id in _FUNCTIONS
            and not node.keywords
            and len(node.args) in {1, 2}
        ):
            try:
                return _FUNCTIONS[node.func.id](*(evaluate(argument) for argument in node.args))
            except (TypeError, ValueError) as exc:
                raise BuiltinToolError("CALCULATION_FAILED", "함수 계산을 완료하지 못했습니다.") from exc
        raise BuiltinToolError("UNSAFE_EXPRESSION", "허용된 숫자와 계산 함수만 사용할 수 있습니다.")

    result = sympy.simplify(evaluate(tree))
    if result.has(sympy.zoo, sympy.nan, sympy.oo, -sympy.oo):
        raise BuiltinToolError("NON_FINITE_RESULT", "유한하지 않은 계산 결과입니다.")
    if result.is_real is False:
        raise BuiltinToolError("NON_REAL_RESULT", "실수 결과만 계산할 수 있습니다.")
    return result


def _parse_iso_datetime(value: str, field: str) -> datetime:
    try:
        parsed = datetime.fromisoformat(value)
    except ValueError as exc:
        try:
            parsed = datetime.combine(date.fromisoformat(value), time.min)
        except ValueError:
            raise BuiltinToolError("INVALID_DATETIME", f"{field}은 ISO 날짜 또는 날짜시간이어야 합니다.") from exc
    return parsed


def _parse_natural_date(expression: str, relative_base: str | None, timezone: str) -> datetime:
    try:
        zone = ZoneInfo(timezone)
    except ZoneInfoNotFoundError as exc:
        raise BuiltinToolError("INVALID_TIMEZONE", "올바른 IANA 시간대를 입력해 주세요.") from exc
    base = _parse_iso_datetime(relative_base, "기준 시각") if relative_base else datetime.now(zone)
    base = base.replace(tzinfo=zone) if base.tzinfo is None else base.astimezone(zone)
    compact = re.sub(r"\s+", "", expression)

    explicit = re.fullmatch(r"(\d{4})년(\d{1,2})월(\d{1,2})일", compact)
    if explicit:
        try:
            return datetime(
                int(explicit.group(1)), int(explicit.group(2)), int(explicit.group(3)), tzinfo=zone
            )
        except ValueError as exc:
            raise BuiltinToolError("INVALID_DATE", "존재하지 않는 날짜입니다.") from exc

    weekday = re.fullmatch(r"(이번주|다음주)([월화수목금토일])요일?", compact)
    if weekday:
        week_offset = 7 if weekday.group(1) == "다음주" else 0
        monday = (base - timedelta(days=base.weekday())).date()
        target = monday + timedelta(days=week_offset + _KOREAN_WEEKDAYS[weekday.group(2)])
        return datetime.combine(target, time.min, zone)

    relative_days = {"오늘": 0, "내일": 1, "모레": 2}
    if compact in relative_days:
        return datetime.combine(base.date() + timedelta(days=relative_days[compact]), time.min, zone)

    parsed = dateparser.parse(
        expression,
        languages=["ko", "en"],
        settings={
            "RELATIVE_BASE": base.replace(tzinfo=None),
            "TIMEZONE": timezone,
            "RETURN_AS_TIMEZONE_AWARE": True,
            "PREFER_DATES_FROM": "future",
        },
    )
    if parsed is None:
        raise BuiltinToolError("DATE_PARSE_FAILED", "날짜 표현을 해석하지 못했습니다.")
    return parsed.astimezone(zone)


def _business_days(
    start: date, end: date, country: str, company_holidays: list[str]
) -> tuple[int, list[str]]:
    if end < start:
        raise BuiltinToolError("INVALID_DATE_RANGE", "종료일은 시작일보다 빠를 수 없습니다.")
    try:
        public_holidays = holidays.country_holidays(country, years=range(start.year, end.year + 1))
    except (KeyError, NotImplementedError) as exc:
        raise BuiltinToolError("UNSUPPORTED_COUNTRY", "지원되는 국가 코드인지 확인해 주세요.") from exc
    try:
        company_dates = {date.fromisoformat(item) for item in company_holidays}
    except ValueError as exc:
        raise BuiltinToolError("INVALID_HOLIDAY", "회사 휴일은 ISO 날짜여야 합니다.") from exc
    excluded: list[str] = []
    count = 0
    current = start
    while current <= end:
        if current.weekday() >= 5 or current in public_holidays or current in company_dates:
            excluded.append(current.isoformat())
        else:
            count += 1
        current += timedelta(days=1)
    return count, excluded


def calculate(*, operation: str, **arguments: Any) -> dict[str, Any]:
    """허용된 계산 작업 하나를 수행한다."""

    if operation == "math":
        result = _safe_expression(str(arguments.get("expression") or ""))
        try:
            decimal = float(sympy.N(result, 15))
        except (TypeError, ValueError) as exc:
            raise BuiltinToolError("NON_REAL_RESULT", "실수 결과만 계산할 수 있습니다.") from exc
        return {"exact": str(result), "decimal": _tidy(decimal)}
    if operation == "unit":
        try:
            quantity = _UNIT_REGISTRY.Quantity(
                float(arguments["amount"]), str(arguments["from_unit"])
            ).to(str(arguments["to_unit"]))
        except (KeyError, TypeError, ValueError, pint.PintError) as exc:
            raise BuiltinToolError("UNIT_CONVERSION_FAILED", "단위와 값을 확인해 주세요.") from exc
        return {"value": _tidy(float(quantity.magnitude)), "unit": f"{quantity.units:~}"}
    if operation == "date":
        parsed = _parse_natural_date(
            str(arguments.get("expression") or ""),
            arguments.get("relative_base"),
            str(arguments.get("timezone") or "Asia/Seoul"),
        )
        return {"datetime": parsed.isoformat(), "timezone": str(parsed.tzinfo)}
    if operation == "duration":
        start = _parse_iso_datetime(str(arguments.get("start") or ""), "시작 시각")
        end = _parse_iso_datetime(str(arguments.get("end") or ""), "종료 시각")
        try:
            seconds = (end - start).total_seconds()
        except TypeError as exc:
            raise BuiltinToolError(
                "MIXED_TIMEZONE", "시작 시각과 종료 시각의 시간대 표기 방식을 맞춰 주세요."
            ) from exc
        return {"seconds": seconds, "days": seconds / 86400}
    if operation == "business_days":
        try:
            start = date.fromisoformat(str(arguments.get("start_date") or ""))
            end = date.fromisoformat(str(arguments.get("end_date") or ""))
        except ValueError as exc:
            raise BuiltinToolError("INVALID_DATE", "시작일과 종료일은 ISO 날짜여야 합니다.") from exc
        count, excluded = _business_days(
            start,
            end,
            str(arguments.get("country") or "KR"),
            [str(item) for item in arguments.get("company_holidays") or []],
        )
        return {"business_days": count, "excluded_dates": excluded, "inclusive": True}
    if operation == "timezone":
        source = _parse_iso_datetime(str(arguments.get("datetime") or ""), "날짜시간")
        try:
            source_zone = ZoneInfo(str(arguments.get("from_timezone") or "Asia/Seoul"))
            target_zone = ZoneInfo(str(arguments.get("to_timezone") or "UTC"))
        except ZoneInfoNotFoundError as exc:
            raise BuiltinToolError("INVALID_TIMEZONE", "올바른 IANA 시간대를 입력해 주세요.") from exc
        source = source.replace(tzinfo=source_zone) if source.tzinfo is None else source.astimezone(source_zone)
        converted = source.astimezone(target_zone)
        return {"datetime": converted.isoformat(), "timezone": str(converted.tzinfo)}
    raise BuiltinToolError("UNSUPPORTED_OPERATION", "지원하지 않는 계산 작업입니다.")
