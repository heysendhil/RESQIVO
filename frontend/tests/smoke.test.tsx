import { render, screen } from "@testing-library/react";
import { expect, test } from "vitest";

test("the test environment renders React components", () => {
  render(<p>RESQIVO</p>);
  expect(screen.getByText("RESQIVO")).toBeInTheDocument();
});
