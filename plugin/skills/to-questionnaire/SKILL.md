---
name: to-questionnaire
description: "Turn a question you cannot answer alone into a questionnaire for a colleague, lawyer or domain expert to fill in."
disable-model-invocation: true
---

# To Questionnaire

Turn something the user cannot answer alone into a **questionnaire**: a
Markdown document the user gives to one person to fill in on their own time, or
to go through together in a meeting. The recipient, such as a lawyer, a
caseworker or another domain expert, holds knowledge the user lacks.

**Grill the send, not the subject.** Ask the user only about the send, which
they can always answer. The questions in the document target the gap between
what the recipient knows and what the user needs.

1. **Who answers, and what do you need back?** Ask both in one round, unless
   the conversation already answers them: the recipient's role, expertise and
   relationship to the user, and the decisions or facts the user cannot settle
   alone. Done when you know what the recipient knows that the user does not,
   and have a concrete list of what the user must be able to decide afterwards.
2. **Write the questionnaire** aimed at that gap, with the structure below, in
   the recipient's language and in plain language, translating the headings and
   labels too. Done when every item from step 1 is covered by a question.
3. **Deliver it** in one fenced `markdown` block in the conversation, ready to
   copy. Write a file only at a path the user names.

Describe the people a case concerns only with synthetic or anonymized
examples: no names, national identity numbers, health details or identifying
combinations of details. Replace any that the user supplies, and say so.

## Structure

Order the questions most important first, since the recipient may answer only
once, and group them under `##` themes when there are more than a handful.
Each question asks one thing and has a labelled answer line directly below it.

```markdown
# <Title>

**Purpose:** <why this questionnaire exists and the decision that depends on it>

**From:** <the user>

**To:** <the recipient>

**How the answers will be used:** <where they go>

## Context

<one paragraph that lets a recipient outside the work answer well>

## How to answer

<deadline and rough effort; partial answers and "I don't know" help, so flag
uncertainty instead of skipping a question>

## <Theme>

### <One question>

_Why this matters: <the decision the answer changes, only when the question
could be misread or invite a throwaway answer>_

**Answer:**

## Anything else?

<anything we did not ask that we should know>
```
