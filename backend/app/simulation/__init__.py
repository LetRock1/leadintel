"""
Simulated learners, clearly marked and kept apart from the CRM's own code.

    population   who they are and the documented buying formula
    effects      the true effect of every CRM step (semi-synthetic ground truth for next-best-action)
    behaviour    what they do on the website, shared by the history and the live simulation
    history      six months of starting history, made with the real CRM code
    live         the same people (and new sign-ups) using the website in real time through the public API

Only the learners are simulated. Everything the CRM does for them (scores, decisions, emails, tasks, learning) is the
production code path; the team works their tasks like anyone else's.
"""
