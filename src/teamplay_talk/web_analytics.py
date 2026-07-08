"""웹페이지 공용 애널리틱스 스니펫.

GA4(gtag.js)를 홈/대시보드/폼 페이지의 <head>에 공통으로 삽입한다.
"""

from __future__ import annotations

GA4_MEASUREMENT_ID = "G-Y258949QT8"

# <head> 최상단에 넣는 GA4 gtag.js 스니펫.
GA4_HEAD = """<!-- Google tag (gtag.js) -->
<script async src="https://www.googletagmanager.com/gtag/js?id=G-Y258949QT8"></script>
<script>
  window.dataLayer = window.dataLayer || [];
  function gtag(){dataLayer.push(arguments);}
  gtag('js', new Date());
  gtag('config', 'G-Y258949QT8');
</script>"""
