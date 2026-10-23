# Third-party notices

## Beautiful UI

The pixel loader's wavefront timing and rendering pattern are adapted from Beautiful UI's LoadingState. The negotiation conversation's tabbed shell, plain reply hierarchy, and fixed scroll region are adapted from components/primitives/ChatComposer.tsx; its scripted content and composer are replaced with real Maxx events and read-only conversation controls. The streaming text reveal (blurred leading edge and caret) is adapted from components/atoms/StreamText.tsx and is applied only to live-arriving events. Interface patterns elsewhere are inspired by its gallery and adapted to Maxx's own data and product flows. No commercial Central Icons package, analytics, newsletter or external example integration is included.

Source: https://github.com/slev12397/beautiful-ui

MIT License

Copyright (c) 2026 Shane Levine

Permission is hereby granted, free of charge, to any person obtaining a copy
of this software and associated documentation files (the "Software"), to deal
in the Software without restriction, including without limitation the rights
to use, copy, modify, merge, publish, distribute, sublicense, and/or sell
copies of the Software, and to permit persons to whom the Software is
furnished to do so, subject to the following conditions:

The above copyright notice and this permission notice shall be included in all
copies or substantial portions of the Software.

THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND, EXPRESS OR
IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF MERCHANTABILITY,
FITNESS FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT. IN NO EVENT SHALL THE
AUTHORS OR COPYRIGHT HOLDERS BE LIABLE FOR ANY CLAIM, DAMAGES OR OTHER
LIABILITY, WHETHER IN AN ACTION OF CONTRACT, TORT OR OTHERWISE, ARISING FROM,
OUT OF OR IN CONNECTION WITH THE SOFTWARE OR THE USE OR OTHER DEALINGS IN THE
SOFTWARE.

## tracking_number_data

The courier tracking-number patterns and check-digit rules in `services/api/maxx/fulfilment/carriers/*.json` are vendored unchanged from tracking_number_data (commit 03af203), with its licence beside them. Maxx's own code in `tracking_numbers.py` reads them; only the regular expressions' named-group syntax is converted at load time for Python.

Source: https://github.com/jkeen/tracking_number_data

MIT License

Copyright (c) 2017 Jeff Keen

Permission is hereby granted, free of charge, to any person obtaining a copy
of this software and associated documentation files (the "Software"), to deal
in the Software without restriction, including without limitation the rights
to use, copy, modify, merge, publish, distribute, sublicense, and/or sell
copies of the Software, and to permit persons to whom the Software is
furnished to do so, subject to the following conditions:

The above copyright notice and this permission notice shall be included in all
copies or substantial portions of the Software.

THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND, EXPRESS OR
IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF MERCHANTABILITY,
FITNESS FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT. IN NO EVENT SHALL THE
AUTHORS OR COPYRIGHT HOLDERS BE LIABLE FOR ANY CLAIM, DAMAGES OR OTHER
LIABILITY, WHETHER IN AN ACTION OF CONTRACT, TORT OR OTHERWISE, ARISING FROM,
OUT OF OR IN CONNECTION WITH THE SOFTWARE OR THE USE OR OTHER DEALINGS IN THE
SOFTWARE.

## Public data

Sanctions screening downloads the U.S. Treasury OFAC Specially Designated Nationals list (`sdn.csv`, `alt.csv`) at run time from sanctionslistservice.ofac.treas.gov. It is a U.S. Government work and is not redistributed in this repository.

## Frontend dependencies

Motion, Lucide React and the self-hosted Manrope font are installed from npm with pinned versions. Their distributed licences remain in their packages. Manrope uses the SIL Open Font License. Generated artwork is illustrative and is never used as evidence for a price or a merchant relationship.
