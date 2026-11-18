# Heading and keyword review database

A standalone review database uses one topic per original top-level heading. Each topic has three to six short attributes selected from keywords in its speech, for 19 topics and 75 attributes. Repeated mentions are collected under the same attribute. Each attribute records the original lines and exact keyword offsets. The database provides separate views for display and evidence.

The source and all 520 stored lines matched the original. Read-only checks verified every attribute’s evidence within its heading and SQLite integrity. The original viewer remains in place. The standalone database, source and topic list are local artifacts.

Build with local reviewed inputs using `python build_topics_db.py transcript.txt reviewed_keywords.json topic_keywords.sqlite`.
