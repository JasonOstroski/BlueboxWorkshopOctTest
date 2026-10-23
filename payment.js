const http = require('node:http');
const { randomUUID } = require('node:crypto');
const port = Number(process.env.PORT || 4004);
const transactionsByOrder = new Map();
const send = (res, status, body) => { res.writeHead(status, { 'content-type': 'application/json' }); res.end(JSON.stringify(body)); };
http.createServer((req, res) => {
  if (req.url === '/health') return send(res, 200, { status: 'ok', service: 'payment' });
  if (req.method !== 'POST' || req.url !== '/charge') return send(res, 404, { error: 'Not found' });
  let body = ''; req.on('data', chunk => { body += chunk; }); req.on('end', () => { const input = JSON.parse(body || '{}'); if (!input.amountCents) return send(res, 400, { error: 'Amount is required' }); const previousPayment = transactionsByOrder.get(input.orderId); if (previousPayment) { console.log(JSON.stringify({ event: 'payment_idempotent_replay', orderId: input.orderId, transactionId: previousPayment.transactionId, attempt: input.attempt })); return send(res, 200, previousPayment); } const transactionId = `txn_${randomUUID().slice(0, 8)}`; const response = { status: 'approved', transactionId }; transactionsByOrder.set(input.orderId, response); console.log(JSON.stringify({ event: 'payment_transaction_created', orderId: input.orderId, transactionId, attempt: input.attempt, amountCents: input.amountCents })); const delay = input.attempt === 1 ? 500 : 0; setTimeout(() => send(res, 200, response), delay); });
}).listen(port, () => console.log(`payment service running at http://localhost:${port}`));
