"""
Pins the contact details on the public marketing pages: the founder's
personal phone number must never appear (in any format), and every page
with a footer offers the business email plus a Book a call link instead.

Pure file reads — no server, no database, no network.
"""

import os
import re

FRONTEND = os.path.abspath(os.path.join(os.path.dirname(__file__), '..', '..', 'frontend'))
PUBLIC_PAGES = ['index.html', 'pricing.html', '404.html']

# 631-697-8711, (631) 697-8711, 631.697.8711, +1 631 697 8711, 6316978711, tel: links
PHONE = re.compile(r'631\D{0,3}697\D{0,3}8711')


def _read(name):
    with open(os.path.join(FRONTEND, name), encoding='utf-8') as f:
        return f.read()


def test_no_public_page_contains_the_personal_phone_number():
    for name in PUBLIC_PAGES:
        html = _read(name)
        assert not PHONE.search(html), f"{name} still shows the personal phone number"
        assert 'tel:' not in html, f"{name} has a tel: link"


def test_footers_offer_business_email_and_book_a_call():
    for name in ['index.html', 'pricing.html']:
        html = _read(name)
        footer = re.search(r'<p class="footer-contact">(.*?)</p>', html, re.S)
        assert footer, f"{name} has no footer-contact line"
        line = footer.group(1)
        assert 'href="mailto:tim@getabstractly.com"' in line, f"{name} footer email is wrong"
        assert 'timmypisano24@gmail.com' not in html, f"{name} still shows the personal email"
        assert re.search(r'href="(index\.html)?#book-demo">Book a call</a>', line), \
            f"{name} footer has no Book a call link"


def test_tim_at_getabstractly_is_the_only_public_email():
    for name in PUBLIC_PAGES:
        emails = set(re.findall(r'[\w.%+-]+@[\w-]+(?:\.[\w-]+)+', _read(name)))
        assert emails <= {'tim@getabstractly.com'}, f"{name} shows other emails: {emails}"


def test_faqs_and_contact_section_link_the_email():
    mailto = 'href="mailto:tim@getabstractly.com"'
    for name, section in [('index.html', 'id="faq"'), ('index.html', 'id="book-demo"'),
                          ('pricing.html', 'id="pricing-faq"')]:
        html = _read(name)
        body = html[html.index(section):]
        body = body[:body.index('</section>')]
        assert mailto in body, f"{name} {section} has no mailto link"


if __name__ == "__main__":
    test_no_public_page_contains_the_personal_phone_number()
    test_footers_offer_business_email_and_book_a_call()
    test_tim_at_getabstractly_is_the_only_public_email()
    test_faqs_and_contact_section_link_the_email()
    print("\nAll public-contact tests passed.")
