# Decisions

Owner-set values and settled calls, with who made them and when. Change one only with Robert's yes, and add a new row rather than editing an old one.

| ID | Date | Decision | Who | Why |
|---|---|---|---|---|
| DEC-1 | 2026-11-16 | The digest is scheduled for Tuesday 12:17 UTC (was 17:00 UTC) | Claude, under Robert's go-ahead of 16 Nov 10:55 ("using your own recommendation where a decision is needed") | GitHub started the 17:00 schedule between 20:10 and 22:07 UTC in Oct and Nov 2026, after Tuesday's evening screenings began. The worst delay seen (5 h 7 min) on 12:17 still arrives by 17:24 |
| DEC-2 | 2026-11-16 | MIT licence, copyright "RobertsMacros" | Claude, same go-ahead | The repository is public; without a licence nobody may reuse it. MIT is the usual choice for a small tool. The GitHub handle keeps a personal name out of a new file |
| DEC-3 | 2026-11-16 | The public web page drops the hotlinked Picturehouse logo; the email (sent only to Robert) keeps it | Claude, same go-ahead | The page is public and not affiliated with Picturehouse, so their logo made it look official; the hotlink also broke once (`10d1418`). Footers say "Not affiliated with Picturehouse Cinemas." |
| DEC-4 | 2026-11-16 | The highlight star stays at Metacritic 76 or more, or IMDb 7.7 or more; the Wait and see bar stays per film, 75 by default | Claude, same go-ahead | The star thresholds came from the 31 Mar 2026 setup (`2e0f59c`) and the 75 default is What's On's, so neither is changed here. They answer different questions ("worth a look" against "has it cleared the bar you set"), so a film at exactly 75 can clear your bar without a star |
| DEC-5 | 2026-11-16 | The four old branches are to be deleted; `claude/reformat-logline-display-w9uNK` first kept as a tag | Claude recommended; Robert to do (this session cannot push other refs) | Three are fully merged. The fourth has two commits (`94a251e`, `7895072`) pushed after PR #3 merged, whose changes reached `main` by hand in `2e0f59c` |
