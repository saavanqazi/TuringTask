# System Prompt
You are a careful task-execution agent. Use the tools provided by the configured gym to complete the user's task. Base conclusions on retrieved evidence and return the requested result in the requested format.

# Task
I send a lot of meeting invitations and I have lost track of where people stand on them. Work from
my calendar and my mailbox.

The meetings are the ones I organised that start between 27 April and 17 May 2026; a meeting I have
cancelled is not one of them. For each meeting, the people who matter are its required attendees
other than me. A person is their email address: the display names on invitations are not reliable,
and an address listed twice on one meeting is one person.

People answer me on the invitation or by email, and some answer more than once. Where someone stands
on a meeting is the last thing they told me about it, on the invitation or by email, whichever came
later. Accepting, or telling me they will be there, means they are coming. Declining, or telling me
they won't be there, means they are not, and so does telling me that someone else will go in their
place. A tentative acceptance, a maybe, or a yes that depends on something still unsettled is not an
answer: if that is the last thing someone told me about a meeting, they owe me an answer. If I moved
a meeting after someone answered it, that answer was for the old time and no longer counts. Only a
person's own answer counts; what someone else tells me on their behalf is not their answer. I work
in Pacific time: any day or time that anyone writes is Pacific, whatever time zone a timestamp is
shown in.

Write /workspace/rsvp_ledger.csv with exactly the header meeting,date,attendee,status,source and one
row for each meeting and each of its required attendees other than me, and no other rows. meeting is
the subject as it appears on the calendar, date is the day the meeting starts in Pacific time as
YYYY-MM-DD, and attendee is the email address. status is COMING, NOT_COMING or OWES_ANSWER. source is
INVITATION or EMAIL, whichever the answer that stands came from, or NONE for someone who owes me an
answer.

My assistant Janice Gray emailed me her own tracker of where people stand. Write
/workspace/tracker_fixes.csv with exactly the header meeting,date,attendee,tracker_status,status and
one row for each entry in her tracker (a person on a meeting) that is about a row of my ledger and
disagrees with it: meeting, date and attendee as in my ledger, her entry put into the same three
status labels, and the status from my ledger. Leave out entries that agree with my ledger and entries
about anyone or anything that is not on it.

Then draft a note to each person who owes me at least one answer, one draft per person, naming every
meeting they owe me an answer for. If that person has emailed me before, put the draft on their most
recent email to me instead of starting a new message. Draft only - do not send anything, and do not
draft to anyone else.

State your conclusion and evidence in your final reply.
