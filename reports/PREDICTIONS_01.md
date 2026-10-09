# Assignment 1 · Predictions

Written before any Part B evaluation run. For each way: predicted passes out of 60,
and the issue I expect it to find hardest.

Direct call — 30/60, 4203: I think 4203 will be the hardest for the direct call because it's about really subtle nuances. CSV errors can be caused by many different file-formatting differences, and the model does not get to investigate the individual files for these nuances. I expect it to pass 4202 and 5206 because it makes it easy to identify the correct file, which is a prerequisite. I expect 20/60 becaused out of the 6 issues, I think only 2 (4202, 4206) make it easy to find the file. So then I add another 10 because they could correctly identify another one by sheer luck.

Workflow — 40/60, 4206: If the user identifies the wrong file, then since there's only one call to extract the search terms, it may search the wrong file. Since it doesn't loop, it might just not get the right answer.  Since workflow can search the actual code, it's less reliant on direct call to specify relevant terms.

Agent 40/60 — 4205: Since this is a question that might not even involve identifying a responsible file, the agent may keep looping on and on without end. The agent is definitely better at looping when it can't find the right search term and re prompting, but it may waste unnecessary steps and fail because it runs out of search time
