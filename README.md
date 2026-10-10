# Sarenakh (سرنخ)

Sarenakh helps a business find people in Telegram groups who need what it sells.

You tell it what you sell. Then you give it the messages of a group, either the JSON export from
Telegram Desktop or just pasted text. It reads the messages, follows the conversations and shows you the
people who are actually looking for something like your product. For each person you see the messages
it based that on, and a reply you can send them. You also see how much it cost to check the messages.

It doesn't send anything by itself. You decide who to reply to.

## Running it

You need Python 3.11 and Node.js. Double-click `start.cmd`. The first time it creates `.env`;
put your OpenAI key in it and double-click again. The site opens at http://localhost:8000.
Sign up and press the sample data button to see how it works.

## Putting it online

The server has to be outside Iran, because OpenAI doesn't accept requests from Iranian IPs.
On a single server you can use `docker compose up -d`. For Kubernetes there's a Helm chart in
`deploy/helm`, and `deploy/helm/DEPLOY.md` explains the steps.

## Tests

```
cd backend
python -m pytest
```
