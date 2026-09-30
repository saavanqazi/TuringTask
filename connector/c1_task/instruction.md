# System Prompt
You are a careful task-execution agent. Use the tools provided by the configured gym to complete the user's task. Base conclusions on retrieved evidence and return the requested result in the requested format.

# Task
I send a lot of meeting invitations and I have stopped checking who actually answered them. Before
these meetings happen I want to know who still owes me a reply.

Look at the meetings I organised on my calendar between 27 April and 17 May 2026, and at who I
invited as a required attendee. A required attendee still owes me an answer if they have not
responded or have only accepted tentatively. Someone who declined has answered me. Optional
attendees do not matter here. Some people answer me by email instead of on the invitation: if
someone has told me in an email that they will or won't be at one of these meetings, that is their
answer, whatever the invitation shows. A maybe is not an answer, and if someone has emailed me about
a meeting more than once, only their latest email about it counts. If I moved a meeting after
someone answered it, on the invitation or by email, that answer was for the old time and no longer
counts. Only a person's own answer counts; something a colleague tells me on their behalf is not
their answer. I work in Pacific time: any day or time that I or anyone else writes ("tomorrow",
"11:00") is Pacific time, whatever time zone a timestamp is shown in.

How you work is checked as well as what you answer: I expect to see the attendee responses read off
the calendar, and my mail checked for each person before anything is drafted.

Five figures. How many meetings I am running in that window. How many of them are still owed an
answer by at least one required attendee. How many people I need to chase. How many answers are still
owed, counting a person once for each meeting they have not answered. And how many of the people I
need to chase have already emailed me at some point.

Write them to /workspace/metrics.json as the top-level keys meetings_i_am_running,
meetings_still_owed_an_answer, people_to_chase, answers_still_owed and
people_to_chase_who_already_emailed_me. Each figure is the number itself, not text and not wrapped
in an object.

Then draft a note to each person I need to chase, one draft per person, naming the meetings they
have not answered. If that person has emailed me before, put the draft on their most recent email
to me instead of starting a new message. Draft only - do not send anything, and do not draft to
anyone else.

State your conclusion and evidence in your final reply.
