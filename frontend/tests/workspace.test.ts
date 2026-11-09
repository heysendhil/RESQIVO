import { describe, expect, test } from "vitest";

import { externalUrl } from "@/lib/safe-url";
import { samplePlans } from "@/lib/sample-plans";
import {
  constraintList,
  emptyRow,
  sampleWorkspaces,
  toDraftRequest,
  toNumberOrText,
  toPlan,
} from "@/lib/workspace";

describe("workspace conversion", () => {
  test("sample workspaces convert back to the original sample plans exactly", () => {
    sampleWorkspaces.forEach((sample, index) => {
      expect(toPlan(sample.workspace)).toEqual(samplePlans[index].plan);
    });
  });

  test.each([
    ["12", 12],
    [" 7 ", 7],
    ["0", 0],
    ["-3", -3],
    ["12.5", "12.5"],
    ["", ""],
    ["1e3", "1e3"],
    ["ten", "ten"],
  ])("%j is sent as %j (whole numbers only; nothing rounded or filled in)", (text, sent) => {
    expect(toNumberOrText(text)).toBe(sent);
  });

  test("draft requests use the backend's field names and only supplied values", () => {
    const workspace = {
      ...sampleWorkspaces[0].workspace,
      constraints: " Road closed \n\n  Night travel only ",
    };

    const request = toDraftRequest(workspace);

    expect(Object.keys(request).sort()).toEqual(
      ["constraints", "needs", "resources", "scenario", "shelters"],
    );
    expect(request.scenario.affected_population).toBe(930);
    expect(request.constraints).toEqual(["Road closed", "Night travel only"]);
    expect(request.resources).toEqual(samplePlans[0].plan.resources);
    expect(request.needs).toEqual([
      { destination_id: "shelter-001", resource_type: "drinking_water", quantity_needed: 6000 },
    ]);
  });

  test("new rows start empty except for enum selections", () => {
    expect(emptyRow("resources")).toEqual({
      resource_id: "",
      name: "",
      resource_type: "food",
      quantity_available: "",
      unit: "",
      location: "",
    });
    expect(constraintList("")).toEqual([]);
  });
});

describe("citation URLs", () => {
  test.each([
    ["https://www.who.int/publications/i/item/9789241516181", true],
    ["http://example.org/a", true],
    ["urn:resqivo:synthetic:SYN-001", false],
    ["javascript:alert(1)", false],
    ["data:text/html,<script>alert(1)</script>", false],
    ["not a url", false],
  ])("%s is a link: %s", (url, isLink) => {
    expect(externalUrl(url) !== null).toBe(isLink);
  });
});
