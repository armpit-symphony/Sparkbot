// Optional live acceptance: uses the host's installed Playwright and RT_OWNER_PASSPHRASE.
// Never saves cookies, keys, screenshots, or traces. All writes use a disposable room.
const { chromium } = require('playwright');
const root = 'https://sparkpitlabs.com';
(async () => {
  const browser = await chromium.launch({ headless: true });
  const owner = await browser.newContext();
  const page = await owner.newPage();
  page.setDefaultTimeout(20000);
  let room, seat, token;
  try {
    await page.goto(root + '/roundtable/login');
    await page.getByPlaceholder('Enter your secret passphrase').fill(process.env.RT_OWNER_PASSPHRASE);
    const loggedIn = page.waitForResponse(r => r.url().endsWith('/api/v1/chat/users/login') && r.request().method() === 'POST');
    await page.getByRole('button', { name: 'Access Sparkbot' }).click();
    const login = await loggedIn;
    if (!login.ok()) throw new Error('Owner login failed');
    token = (await login.json()).access_token;
    await page.waitForURL(url => !url.pathname.endsWith('/login'));
    await page.goto(root + '/roundtable/meeting/94c397db-d48e-4489-a91d-c9948db89b2b');
    await page.getByText('Hello Phil! Atlas here from Codex.', { exact: false }).first().waitFor();
    await page.getByText('People & agents', { exact: true }).waitFor();
    console.log('PASS: owner browser login, existing Atlas hello visible, People & agents panel visible.');
    const headers = { Authorization: 'Bearer ' + token };
    const created = await owner.request.post(root + '/api/v1/chat/rooms/', {
      headers, data: { name: 'RT008 disposable browser acceptance' },
    });
    if (!created.ok()) throw new Error('Temporary room creation failed');
    room = (await created.json()).id;
    await page.goto(root + '/roundtable/meeting/' + room);
    await page.getByRole('button', { name: 'Invite', exact: true }).click();
    await page.getByRole('textbox', { name: 'Name', exact: true }).fill('RT008 Guest ' + Date.now());
    await page.getByRole('button', { name: 'Person', exact: true }).click();
    const invited = page.waitForResponse(r => r.url().endsWith('/rooms/' + room + '/seats') && r.request().method() === 'POST');
    await page.getByRole('button', { name: 'Create seat', exact: true }).click();
    const invitation = await invited;
    if (!invitation.ok()) throw new Error('Guest invite failed');
    seat = (await invitation.json()).id;
    const link = await page.getByTestId('roundtable-invite-result').locator('textarea').inputValue();
    const guest = await browser.newContext();
    const guestPage = await guest.newPage();
    await guestPage.goto(link);
    await guestPage.getByRole('textbox', { name: 'Message', exact: true }).fill('RT008 guest browser acceptance');
    await guestPage.getByRole('button', { name: 'Send', exact: true }).click();
    await page.getByText('RT008 guest browser acceptance', { exact: true }).first().waitFor();
    if (new URL(guestPage.url()).hash) throw new Error('Guest key fragment not removed');
    const editor = page.getByPlaceholder('Message the room…', { exact: true });
    await editor.fill('RT008 owner reply without models');
    await editor.press('Enter');
    await guestPage.getByText('RT008 owner reply without models', { exact: true }).first().waitFor();
    await page.getByRole('button', { name: 'Remove', exact: true }).click();
    await page.getByRole('button', { name: 'Sure?', exact: true }).click();
    await guestPage.getByText(/revoked|no longer valid/i).first().waitFor();
    console.log('PASS: in-app Person invite, guest link, fragment removal, live guest message, model-free owner reply, guest revocation.');
    await guest.close();
  } finally {
    if (room && token) {
      const headers = { Authorization: 'Bearer ' + token };
      if (seat) await owner.request.delete(root + `/api/v1/chat/rooms/${room}/seats/${seat}`, { headers });
      const removed = await owner.request.delete(root + '/api/v1/chat/rooms/' + room, { headers });
      if (!removed.ok()) console.error('Temporary room cleanup requires follow-up.');
    }
    await browser.close();
  }
})().catch(error => {
  console.error(String(error.message).replace(/rts_[^\s"'&]+/g, '[REDACTED]').replace(/#key=[^\s]+/g, '#[REDACTED]'));
  process.exitCode = 1;
});
