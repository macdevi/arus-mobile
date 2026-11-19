import subprocess
from datetime import datetime
from zoneinfo import ZoneInfo
from playwright.sync_api import sync_playwright, expect

seed="import os,domain as D; from werkzeug.security import generate_password_hash; p=os.environ['ARUS_NEXT_DB']; D.initialize(p); c=__import__('sqlite3').connect(p); D.put(c,'password_hash',generate_password_hash('ci-password-not-for-production')); D.put(c,'auth_version','ci'); c.commit(); c.close()"
subprocess.run(['docker','exec','arus-next-ci','python','-c',seed],check=True)
today=datetime.now(ZoneInfo('Asia/Seoul')).date().isoformat()
with sync_playwright() as p:
    browser=p.chromium.launch()
    page=browser.new_page(viewport={'width':390,'height':844})
    errors=[]
    page.on('pageerror',lambda error:errors.append(str(error)))
    page.goto('http://127.0.0.1:18081')
    page.locator('#loginForm input').fill('ci-password-not-for-production')
    page.locator('#loginForm button').click()
    expect(page.locator('#application')).to_be_visible()
    def tab(name): page.locator('[data-tab='+name+']').click()
    def submit(op,values):
        form=page.locator('form[data-op='+op+']')
        for key,value in values.items():
            field=form.locator('[name='+key+']')
            if field.evaluate('(e)=>e.tagName')=='SELECT': field.select_option(str(value))
            else: field.fill(str(value))
        with page.expect_response(lambda response:response.url.endswith('/api/action') and response.request.method=='POST') as result: form.locator('button').click()
        assert result.value.status==200,result.value.text()
        expect(form.locator('button')).to_be_enabled()
    tab('settings')
    submit('manual_rate',{'day':today,'rate':'11.5'})
    submit('opening',{'KRW':10000,'IDR':1000000,'day':today})
    tab('transactions')
    submit('transaction',{'kind':'expense','currency':'IDR','amount':100,'day':today,'description':'Browser test','category':'Test'})
    tab('savings')
    submit('goal',{'name':'Target browser','currency':'IDR','target':1000000})
    submit('allocate',{'goal_id':'1','currency':'IDR','delta':400,'day':today})
    tab('loans')
    submit('loan',{'name':'Cicilan won','currency':'KRW','installment':100,'count':2,'first_due':today,'due_day':31})
    submit('pay',{'loan_id':'1','day':today})
    data=page.request.get('http://127.0.0.1:18081/api/data').json()
    assert data['balances']=={'KRW':9900,'IDR':999900},data
    assert data['free']['IDR']==999500,data
    assert data['loans'][0]['remaining_count']==1,data
    assert not errors,errors
    page.locator('#logout').click()
    expect(page.locator('#login')).to_be_visible()
    browser.close()
print('Mobile browser smoke passed.')
