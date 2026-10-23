import http from 'k6/http';
import { Counter } from 'k6/metrics';
import { check, sleep } from 'k6';

const baseUrl = __ENV.TARGET_URL || 'http://shop:8088';
const products = ['aurora-mug', 'signal-notebook', 'orbit-lamp', 'cloud-socks', 'field-bag', 'night-hoodie'];
const duplicateCharges = new Counter('duplicate_charges');

export const options = {
  vus: Number(__ENV.VUS || 10),
  duration: __ENV.DURATION || '60s',
  thresholds: {
    http_req_failed: ['rate<0.01'],
    duplicate_charges: ['count==0'],
  },
};

function jsonRequest(method, path, payload, tags) {
  return http.request(method, `${baseUrl}${path}`, payload ? JSON.stringify(payload) : null, {
    headers: { 'Content-Type': 'application/json' },
    tags,
  });
}

export default function () {
  const userId = `loadgen-${__VU}-${__ITER}`;
  const tags = { workload: 'workshop-shop', user_id: userId };

  const catalog = http.get(`${baseUrl}/api/products`, { tags: { ...tags, operation: 'catalog' } });
  check(catalog, { 'catalog responds': response => response.status === 200 });

  products.slice(0, 4).forEach(productId => {
    const add = jsonRequest('POST', `/api/cart?userId=${userId}`, { productId, quantity: 1 }, { ...tags, operation: 'cart_add' });
    check(add, { 'cart accepts item': response => response.status === 200 });
  });

  const cart = http.get(`${baseUrl}/api/cart?userId=${userId}`, { tags: { ...tags, operation: 'cart_read' } });
  check(cart, { 'cart responds': response => response.status === 200 });

  if (__ITER % 3 === 0) {
    const checkout = jsonRequest('POST', `/api/checkout?userId=${userId}`, {
      email: `loadgen-${__VU}@example.com`,
      cardNumber: '4242424242424242',
      shipping: { firstName: 'Load', lastName: 'Generator', address: '1 Workshop Way', city: 'Localhost', postalCode: '8088' },
    }, { ...tags, operation: 'checkout' });
    check(checkout, { 'checkout responds': response => response.status === 200 });
    if (checkout.status === 200) {
      const duplicateOf = checkout.json('payment.duplicateOf');
      if (duplicateOf) duplicateCharges.add(1);
      check(checkout, { 'payment is idempotent': () => !duplicateOf });
    }
  }

  sleep(0.5);
}
