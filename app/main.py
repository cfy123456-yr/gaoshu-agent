from fastapi import FastAPI, HTTPException, Query
from pydantic import BaseModel, Field
from sympy import Limit, diff, integrate, latex, simplify, sympify
from sympy.parsing.sympy_parser import (
    implicit_multiplication_application,
    parse_expr,
    standard_transformations,
)


app = FastAPI(title="知微数学验证服务", version="0.1.0")


class VerifyRequest(BaseModel):
    expression: str = Field(min_length=1)
    variable: str = Field(default="x", min_length=1)
    candidate: str | None = None


class VerifyResponse(BaseModel):
    expression: str
    variable: str
    derivative: str
    derivative_latex: str
    candidate: str | None
    is_correct: bool | None


class IntegrateRequest(BaseModel):
    expression: str = Field(min_length=1)
    variable: str = Field(default="x", min_length=1)
    lower: str | None = None
    upper: str | None = None
    candidate: str | None = None


class IntegrateResponse(BaseModel):
    expression: str
    variable: str
    integral: str
    integral_latex: str
    candidate: str | None
    is_correct: bool | None


class LimitRequest(BaseModel):
    expression: str = Field(min_length=1)
    variable: str = Field(default="x", min_length=1)
    point: str = Field(default="0", min_length=1)
    direction: str | None = None
    candidate: str | None = None


class LimitResponse(BaseModel):
    expression: str
    variable: str
    point: str
    direction: str | None
    limit: str
    limit_latex: str
    candidate: str | None
    is_correct: bool | None


def parse_math_expression(value: str):
    normalized = value.strip().replace("^", "**")
    transformations = standard_transformations + (implicit_multiplication_application,)
    return parse_expr(normalized, transformations=transformations)


def parse_direction(value: str | None) -> str | None:
    if value is None or not value.strip() or value.strip() == "+-":
        return None

    direction = value.strip()
    if direction not in {"+", "-"}:
        raise ValueError("方向只能是 '+'、'-' 或空")

    return direction


@app.get("/health")
def health_check():
    return {"status": "ok", "service": "math-tool"}


@app.post("/verify", response_model=VerifyResponse)
def verify_derivative(request: VerifyRequest):
    try:
        variable = sympify(request.variable)
        expression = parse_math_expression(request.expression)
        derivative = diff(expression, variable)
        candidate = parse_math_expression(request.candidate) if request.candidate else None
        is_correct = simplify(derivative - candidate) == 0 if candidate is not None else None
    except Exception as exc:
        raise HTTPException(status_code=400, detail=f"表达式无法解析: {exc}") from exc

    return VerifyResponse(
        expression=str(expression),
        variable=str(variable),
        derivative=str(derivative),
        derivative_latex=latex(derivative),
        candidate=str(candidate) if candidate is not None else None,
        is_correct=is_correct,
    )


@app.post("/verify-query", response_model=VerifyResponse)
def verify_derivative_query(
    expression: str = Query(min_length=1),
    variable: str = Query(default="x", min_length=1),
    candidate: str | None = Query(default=None),
):
    return verify_derivative(
        VerifyRequest(
            expression=expression,
            variable=variable,
            candidate=candidate,
        )
    )


@app.post("/integrate", response_model=IntegrateResponse)
def calculate_integral(request: IntegrateRequest):
    try:
        variable = sympify(request.variable)
        expression = parse_math_expression(request.expression)
        lower_value = request.lower.strip() if request.lower and request.lower.strip() else None
        upper_value = request.upper.strip() if request.upper and request.upper.strip() else None
        candidate_value = (
            request.candidate.strip() if request.candidate and request.candidate.strip() else None
        )

        if lower_value is not None and upper_value is not None:
            lower = parse_math_expression(lower_value)
            upper = parse_math_expression(upper_value)
            integral = integrate(expression, (variable, lower, upper))
        else:
            integral = integrate(expression, variable)

        candidate = parse_math_expression(candidate_value) if candidate_value else None
        if candidate is None:
            is_correct = None
        elif lower_value is not None and upper_value is not None:
            is_correct = simplify(integral - candidate) == 0
        else:
            is_correct = simplify(diff(integral - candidate, variable)) == 0
    except Exception as exc:
        raise HTTPException(status_code=400, detail=f"表达式无法解析: {exc}") from exc

    return IntegrateResponse(
        expression=str(expression),
        variable=str(variable),
        integral=str(integral),
        integral_latex=latex(integral),
        candidate=str(candidate) if candidate is not None else None,
        is_correct=is_correct,
    )


@app.post("/integrate-query", response_model=IntegrateResponse)
def calculate_integral_query(
    expression: str = Query(min_length=1),
    variable: str = Query(default="x", min_length=1),
    lower: str | None = Query(default=None),
    upper: str | None = Query(default=None),
    candidate: str | None = Query(default=None),
):
    return calculate_integral(
        IntegrateRequest(
            expression=expression,
            variable=variable,
            lower=lower,
            upper=upper,
            candidate=candidate,
        )
    )


@app.post("/limit", response_model=LimitResponse)
def calculate_limit(request: LimitRequest):
    try:
        variable = sympify(request.variable)
        expression = parse_math_expression(request.expression)
        point = parse_math_expression(request.point)
        direction = parse_direction(request.direction)
        candidate = parse_math_expression(request.candidate) if request.candidate else None

        if direction is None:
            limit_expression = Limit(expression, variable, point)
        else:
            limit_expression = Limit(expression, variable, point, direction)
        limit_value = limit_expression.doit()
        if getattr(limit_value, "has", lambda *_: False)(Limit):
            raise ValueError("极限无法确定，可能需要补充条件或改写表达式")

        is_correct = simplify(limit_value - candidate) == 0 if candidate is not None else None
    except Exception as exc:
        raise HTTPException(status_code=400, detail=f"表达式无法解析: {exc}") from exc

    return LimitResponse(
        expression=str(expression),
        variable=str(variable),
        point=str(point),
        direction=direction,
        limit=str(limit_value),
        limit_latex=latex(limit_value),
        candidate=str(candidate) if candidate is not None else None,
        is_correct=is_correct,
    )


@app.post("/limit-query", response_model=LimitResponse)
def calculate_limit_query(
    expression: str = Query(min_length=1),
    variable: str = Query(default="x", min_length=1),
    point: str = Query(default="0", min_length=1),
    direction: str | None = Query(default=None),
    candidate: str | None = Query(default=None),
):
    return calculate_limit(
        LimitRequest(
            expression=expression,
            variable=variable,
            point=point,
            direction=direction,
            candidate=candidate,
        )
    )
