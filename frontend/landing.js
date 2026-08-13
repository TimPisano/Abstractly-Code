/**
 * Landing page waitlist form: posts to the backend and swaps in a
 * confirmation state instead of navigating away.
 */

const API_BASE_URL = 'http://localhost:5000';

document.getElementById('waitlistForm').addEventListener('submit', async (e) => {
    e.preventDefault();

    const emailInput = document.getElementById('waitlistEmail');
    const errorEl = document.getElementById('waitlistError');
    const submitBtn = document.getElementById('waitlistSubmitBtn');
    const email = emailInput.value.trim();

    errorEl.classList.remove('show');
    submitBtn.disabled = true;
    submitBtn.textContent = 'Joining...';

    try {
        const response = await fetch(`${API_BASE_URL}/waitlist`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ email }),
        });
        const data = await response.json().catch(() => ({}));

        if (!response.ok) {
            throw new Error(data.error || 'Something went wrong. Please try again.');
        }

        document.getElementById('heroFormWrap').classList.add('submitted');
        document.getElementById('waitlistConfirm').classList.add('show');
    } catch (err) {
        errorEl.textContent = err.message;
        errorEl.classList.add('show');
        submitBtn.disabled = false;
        submitBtn.textContent = 'Join the waitlist';
    }
});
