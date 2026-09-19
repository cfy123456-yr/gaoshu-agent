from fastapi import FastAPI, HTTPException, Query
from pydantic import BaseModel, Field
from sympy import diff, integrate, latex, simplify, sympify
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


def parse_math_expression(value: str):
    normalized = value.strip().replace("^", "**")
    transformations = standard_transformations + (implicit_multiplication_application,)
    return parse_expr(normalized, transformations=transformations)


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
