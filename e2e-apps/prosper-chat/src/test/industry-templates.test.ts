import { describe, expect, it } from "vitest";

import {
  industryTemplates,
  normalizeIndustryTemplate,
  type IndustryTemplate,
} from "@/data/industryTemplates";

describe("industryTemplates", () => {
  it("keeps each template onboarding-ready with stable service and faq shapes", () => {
    expect(industryTemplates.length).toBeGreaterThan(0);

    for (const template of industryTemplates) {
      expect(template.id).toBeTruthy();
      expect(template.name).toBeTruthy();
      expect(template.icon).toBeTruthy();
      expect(template.services.length).toBeGreaterThan(0);
      expect(template.faqs.length).toBeGreaterThan(0);

      for (const service of template.services) {
        expect(service.name).toBeTruthy();
        expect(service.duration_minutes).toBeGreaterThan(0);
        expect(service.price_text).toBeTruthy();
        expect(service.description === undefined || service.description.length > 0).toBe(true);
      }

      for (const faq of template.faqs) {
        expect(faq.question).toBeTruthy();
        expect(faq.answer).toBeTruthy();
      }
    }
  });

  it("normalizes template seed content without changing onboarding field names", () => {
    const template: IndustryTemplate = {
      id: " custom-template ",
      name: " Custom Template ",
      icon: industryTemplates[0].icon,
      services: [
        {
          name: " Intro Call ",
          duration_minutes: 15,
          price_text: " Free ",
          description: "  ",
        },
      ],
      faqs: [
        {
          question: " What happens next? ",
          answer: " We reach out within one business day. ",
        },
      ],
    };

    expect(normalizeIndustryTemplate(template)).toEqual({
      id: "custom-template",
      name: "Custom Template",
      icon: template.icon,
      services: [
        {
          name: "Intro Call",
          duration_minutes: 15,
          price_text: "Free",
          description: undefined,
        },
      ],
      faqs: [
        {
          question: "What happens next?",
          answer: "We reach out within one business day.",
        },
      ],
    });
  });
});
