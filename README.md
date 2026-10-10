# Sarenakh (سرنخ)

Sarenakh helps a business find people in Telegram groups and on X (Twitter) who need what it sells.

You tell it what you sell, or give it the link to your product page and it reads the details from there.
Then you give it messages to look through: the JSON export of a Telegram group, pasted text, or a search
of recent Persian posts on X. It reads the messages, follows the conversations and shows you the
people who are actually looking for something like your product. For each person you see the messages
it based that on, and a reply you can send them. You also see how much it cost to check the messages.

It doesn't send anything by itself. You decide who to reply to.

## Running it

You need Python 3.11 and Node.js. Double-click `start.cmd`. The first time it creates `.env`;
put your OpenAI key in it and double-click again. The site opens at http://localhost:8000.
Sign up and press the sample data button to see how it works.

To search X, put an X API bearer token in `.env` as `X_BEARER_TOKEN`. X charges for every post it
returns (about $0.005), so the same search is reused for a day and later searches only fetch new posts.

## Putting it online

The server has to be outside Iran, because OpenAI doesn't accept requests from Iranian IPs.
On a single server you can use `docker compose up -d`. For Kubernetes there's a Helm chart in
`deploy/helm`, and `deploy/helm/DEPLOY.md` explains the steps.

## Tests

```
cd backend
python -m pytest
```
