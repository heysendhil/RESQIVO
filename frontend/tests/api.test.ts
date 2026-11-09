import { describe, expect, test, vi } from "vitest";

import {
  API_BASE_URL,
  ApiError,
  askQuestion,
  draftPlan,
  getHealth,
  reviewPlan,
  validatePlan,
} from "@/lib/api";

import {
  answered,
  draftRequest,
  draftResponse,
  jsonResponse,
  plan,
  reviewResponse,
  stubFetch,
  validResult,
} from "./fixtures";

describe("endpoint requests", () => {
  test("uses the configured base URL", () => {
    expect(API_BASE_URL).toBe("http://api.test");
  });

  test("GET /health", async () => {
    const fetchMock = stubFetch(jsonResponse({ status: "ok", service: "RESQIVO" }));

    await expect(getHealth()).resolves.toEqual({ status: "ok", service: "RESQIVO" });
    const [url, init] = fetchMock.mock.calls[0];
    expect(url).toBe("http://api.test/health");
    expect(init.method).toBe("GET");
    expect(init.body).toBeUndefined();
  });

  test.each([
    ["/validate", () => validatePlan(plan), plan, validResult],
    ["/answer", () => askQuestion("How is water stored?"), { question: "How is water stored?" }, answered],
    [
      "/review",
      () => reviewPlan("Check this plan", plan),
      { question: "Check this plan", plan },
      reviewResponse,
    ],
    ["/review", () => reviewPlan("Only a question", null), { question: "Only a question", plan: null }, { ...reviewResponse, plan_review: null }],
    ["/draft-plan", () => draftPlan(draftRequest), draftRequest, draftResponse],
  ])("POST %s sends the backend schema", async (path, call, expectedBody, response) => {
    const fetchMock = stubFetch(jsonResponse(response));

    await expect(call()).resolves.toEqual(response);
    const [url, init] = fetchMock.mock.calls[0];
    expect(url).toBe(`http://api.test${path}`);
    expect(init.method).toBe("POST");
    expect(init.headers).toEqual({ "Content-Type": "application/json" });
    expect(JSON.parse(init.body)).toEqual(expectedBody);
  });
});

describe("error mapping", () => {
  async function failure(response: Response): Promise<ApiError> {
    stubFetch(response);
    try {
      await validatePlan(plan);
    } catch (error) {
      expect(error).toBeInstanceOf(ApiError);
      return error as ApiError;
    }
    throw new Error("expected an ApiError");
  }

  test.each([
    [413, { detail: "Request body too large." }, "payload_too_large", /too large.*413/],
    [502, { detail: "The language model did not return a usable answer." }, "model_error", /did not return a usable result/],
    [503, { detail: "Question answering is not configured." }, "unavailable", /not configured on the server/],
    [503, { detail: "Knowledge retrieval is unavailable." }, "unavailable", /Knowledge retrieval is unavailable/],
    [503, { detail: "anything else" }, "unavailable", /temporarily unavailable/],
    [504, { detail: "The request did not complete in time." }, "timeout", /did not complete in time/],
    [500, { detail: "Internal server error." }, "server_error", /unexpected error \(HTTP 500\)/],
    [400, { detail: "Invalid Content-Length header." }, "bad_request", /could not read/],
  ])("HTTP %i maps to a fixed message", async (status, body, kind, message) => {
    const error = await failure(jsonResponse(body, status));

    expect(error.kind).toBe(kind);
    expect(error.status).toBe(status);
    expect(error.message).toMatch(message);
  });

  test("HTTP 422 lists field errors without the body prefix", async () => {
    const error = await failure(
      jsonResponse(
        {
          detail: [
            {
              type: "greater_than_equal",
              loc: ["body", "resources", 0, "quantity_available"],
              msg: "Input should be greater than or equal to 0",
              input: -1,
            },
            { loc: ["body"], msg: "Field required" },
          ],
        },
        422,
      ),
    );

    expect(error.kind).toBe("invalid_request");
    expect(error.fieldErrors).toEqual([
      {
        field: "resources.0.quantity_available",
        message: "Input should be greater than or equal to 0",
      },
      { field: "request", message: "Field required" },
    ]);
  });

  test("raw error bodies are never shown", async () => {
    const error = await failure(
      jsonResponse({ detail: "Traceback (most recent call last): sk-ant-secret" }, 500),
    );

    expect(error.message).not.toMatch(/Traceback|sk-ant-secret/);
  });

  test("network failures name the API base URL", async () => {
    vi.stubGlobal("fetch", vi.fn().mockRejectedValue(new TypeError("Failed to fetch")));

    await expect(getHealth()).rejects.toMatchObject({
      kind: "network",
      message: expect.stringContaining("http://api.test"),
    });
  });

  test("non-JSON success responses are rejected", async () => {
    stubFetch(new Response("<html>proxy page</html>", { status: 200 }));

    await expect(getHealth()).rejects.toMatchObject({ kind: "unexpected_response" });
  });

  test.each([
    ["/validate", () => validatePlan(plan), { valid: "yes", violations: [] }],
    ["/answer", () => askQuestion("q"), { ...answered, citations: [{ label: "P1" }] }],
    ["/review", () => reviewPlan("q", plan), { ...reviewResponse, plan_review: { corrected: true } }],
    ["/draft-plan", () => draftPlan(draftRequest), { ...draftResponse, status: "dispatched" }],
  ])("unexpected %s response shapes are rejected", async (_path, call, body) => {
    stubFetch(jsonResponse(body));

    await expect(call()).rejects.toMatchObject({ kind: "unexpected_response" });
  });

  test("aborted requests are not reported as network failures", async () => {
    vi.stubGlobal(
      "fetch",
      vi.fn().mockRejectedValue(new DOMException("aborted", "AbortError")),
    );

    await expect(getHealth()).rejects.toMatchObject({ name: "AbortError" });
  });
});
