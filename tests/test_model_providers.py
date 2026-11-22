import io
import json
import unittest
import urllib.error
from unittest.mock import Mock, patch

from hyperpass.model_providers import (
    AnthropicProvider, GeminiProvider, RoutedProvider, ProviderError,
    CHECK_SCHEMA, _NoRedirect, _request, list_models, make_provider,
    reasoning_options, validate_model_name,
)

KEY='test-secret-not-a-real-key'


def claude_result(text='{"ok":true}'):
    return {'id':'message-1','stop_reason':'end_turn','content':[{'type':'text','text':text}],
            'usage':{'input_tokens':4,'output_tokens':7}}


def gemini_result(text='{"ok":true}'):
    return {'responseId':'response-1','candidates':[{'finishReason':'STOP',
            'content':{'parts':[{'text':text}]}}],
            'usageMetadata':{'promptTokenCount':4,'candidatesTokenCount':7,'totalTokenCount':15}}


class ModelTransportTests(unittest.TestCase):
    @patch('hyperpass.model_providers._request')
    def test_claude_native_schema_and_effort_coexist(self,request):
        request.return_value=claude_result()
        result=AnthropicProvider(KEY,'claude-sonnet-4-6',reasoning='medium').complete('rules',{'x':1},schema=CHECK_SCHEMA)
        args=request.call_args.args
        self.assertEqual(args[:3],('anthropic','POST','https://api.anthropic.com/v1/messages'))
        self.assertEqual(args[4]['output_config'],{'effort':'medium','format':{'type':'json_schema','schema':CHECK_SCHEMA}})
        self.assertEqual(args[4]['thinking'],{'type':'adaptive','display':'omitted'})
        self.assertEqual(result['data'],{'ok':True})
        self.assertEqual(result['usage']['total_tokens'],11)
        self.assertNotIn(KEY,json.dumps(result))

    @patch('hyperpass.model_providers._request')
    def test_claude_search_uses_tool_and_keeps_final_json(self,request):
        raw=claude_result()
        raw['content'].insert(0,{'type':'text','text':'Searching sources.'})
        raw['content'][-1]['citations']=[{'type':'web_search_result_location','url':'https://example.org/evidence','title':'Evidence'}]
        request.return_value=raw
        result=AnthropicProvider(KEY,'claude-sonnet-4-6','high').complete('rules',{},schema=CHECK_SCHEMA,web_search=True)
        body=request.call_args.args[4]
        self.assertEqual(body['tools'][0]['name'],'web_search')
        self.assertNotIn('format',body['output_config'])
        self.assertEqual(body['output_config']['effort'],'high')
        self.assertIn('"additionalProperties": false',body['system'])
        self.assertEqual(result['data'],{'ok':True})
        self.assertEqual(result['citations'][0]['url'],'https://example.org/evidence')
        self.assertEqual(request.call_count,1)

    @patch('hyperpass.model_providers._request')
    def test_claude_46_max_activates_thinking_and_default_stays_default(self,request):
        request.return_value=claude_result()
        AnthropicProvider(KEY,'claude-sonnet-4-6','max').complete('',{},schema=CHECK_SCHEMA)
        self.assertEqual(request.call_args.args[4]['output_config']['effort'],'max')
        self.assertEqual(request.call_args.args[4]['thinking']['type'],'adaptive')
        AnthropicProvider(KEY,'claude-sonnet-4-6').complete('',{},schema=CHECK_SCHEMA)
        self.assertNotIn('thinking',request.call_args.args[4])
        self.assertNotIn('effort',request.call_args.args[4]['output_config'])
        AnthropicProvider(KEY,'claude-opus-5-5','max').complete('',{},schema=CHECK_SCHEMA)
        self.assertNotIn('thinking',request.call_args.args[4])
        self.assertEqual(request.call_args.args[4]['output_config']['effort'],'max')

    @patch('hyperpass.model_providers._request')
    def test_claude_search_errors_are_not_success(self,request):
        raw=claude_result()
        raw['content'].append({'type':'web_search_tool_result','content':{'type':'web_search_tool_result_error','error_code':'max_uses_exceeded'}})
        request.return_value=raw
        with self.assertRaisesRegex(ProviderError,'검색이 실패'):
            AnthropicProvider(KEY,'claude-sonnet-4-6').complete('',{},schema=CHECK_SCHEMA,web_search=True)

    @patch('hyperpass.model_providers._request')
    def test_claude_pause_and_truncation_never_complete_or_auto_resume(self,request):
        for reason in ('pause_turn','max_tokens','refusal','tool_use'):
            raw=claude_result(); raw['stop_reason']=reason; request.return_value=raw
            with self.subTest(reason=reason),self.assertRaises(ProviderError):
                AnthropicProvider(KEY,'claude-sonnet-4-6').complete('',{},schema=CHECK_SCHEMA)
        self.assertEqual(request.call_count,4)

    @patch('hyperpass.model_providers._request')
    def test_gemini_native_schema_and_thinking_config(self,request):
        request.return_value=gemini_result()
        result=GeminiProvider(KEY,'models/gemini-3-flash-preview','medium').complete('rules',{},schema=CHECK_SCHEMA)
        body=request.call_args.args[4]
        self.assertTrue(request.call_args.args[2].endswith('/gemini-3-flash-preview:generateContent'))
        self.assertEqual(body['generationConfig']['thinkingConfig'],{'thinkingLevel':'MEDIUM'})
        self.assertEqual(body['generationConfig']['responseJsonSchema'],CHECK_SCHEMA)
        self.assertEqual(result['usage']['total_tokens'],15)
        self.assertEqual(result['data'],{'ok':True})

    @patch('hyperpass.model_providers._request')
    def test_gemini_25_uses_explicit_token_budget_not_thinking_level(self,request):
        request.return_value=gemini_result()
        GeminiProvider(KEY,'gemini-2.5-flash','budget_4096').complete('',{},schema=CHECK_SCHEMA)
        body=request.call_args.args[4]
        self.assertEqual(body['generationConfig']['thinkingConfig'],{'thinkingBudget':4096})
        self.assertGreater(body['generationConfig']['maxOutputTokens'],4096)
        with self.assertRaises(ProviderError): GeminiProvider(KEY,'gemini-2.5-pro','high')

    @patch('hyperpass.model_providers._request')
    def test_gemini_search_citations_and_hidden_thought_not_used_as_json(self,request):
        raw=gemini_result()
        candidate=raw['candidates'][0]
        candidate['content']['parts'].insert(0,{'thought':True,'text':'private intermediate text'})
        candidate['groundingMetadata']={'webSearchQueries':['company filing'],
            'searchEntryPoint':{'renderedContent':'<div>Google search suggestions</div>'},
            'groundingChunks':[{'web':{'uri':'https://example.org/filing','title':'Filing'}},
                               {'web':{'uri':'javascript:alert(1)','title':'bad'}}]}
        request.return_value=raw
        result=GeminiProvider(KEY,'gemini-3-flash-preview').complete('',{},schema=CHECK_SCHEMA,web_search=True)
        body=request.call_args.args[4]
        self.assertEqual(body['tools'],[{'google_search':{}}])
        self.assertNotIn('responseJsonSchema',body['generationConfig'])
        self.assertEqual(result['citations'],[{'url':'https://example.org/filing','title':'Filing'}])
        self.assertEqual(result['grounding_queries'],['company filing'])
        self.assertEqual(result['search_suggestions_html'],'<div>Google search suggestions</div>')
        self.assertNotIn('private',json.dumps(result))
        self.assertEqual(request.call_count,1)

    @patch('hyperpass.model_providers._request')
    def test_gemini_search_suggestion_html_is_bounded_not_truncated(self,request):
        raw=gemini_result()
        raw['candidates'][0]['groundingMetadata']={'searchEntryPoint':{'renderedContent':'가'*22000}}
        request.return_value=raw
        with self.assertRaisesRegex(ProviderError,'검색 제안'):
            GeminiProvider(KEY,'gemini-3-flash-preview').complete('',{},schema=CHECK_SCHEMA,web_search=True)

    @patch('hyperpass.model_providers._request')
    def test_invalid_json_and_blocked_results_fail(self,request):
        request.return_value=gemini_result('not JSON')
        with self.assertRaisesRegex(ProviderError,'JSON'):
            GeminiProvider(KEY,'gemini-3-flash-preview').complete('',{},schema=CHECK_SCHEMA)
        for raw in ({'candidates':[]}, {'candidates':[{'finishReason':'MAX_TOKENS'}]}):
            request.return_value=raw
            with self.assertRaises(ProviderError):
                GeminiProvider(KEY,'gemini-3-flash-preview').complete('',{},schema=CHECK_SCHEMA)

    @patch('hyperpass.model_providers._request')
    def test_connection_checks_verify_actual_structured_reply(self,request):
        for cls,model,response in [(AnthropicProvider,'claude-sonnet-4-6',claude_result()),
                                   (GeminiProvider,'gemini-3-flash-preview',gemini_result())]:
            request.return_value=response
            self.assertTrue(cls(KEY,model).check()['ok'])
            body=request.call_args.args[4]
            limit=body.get('max_tokens',body.get('generationConfig',{}).get('maxOutputTokens'))
            self.assertEqual(limit,1024)
        request.return_value=claude_result('{"ok":false}')
        with self.assertRaises(ProviderError): AnthropicProvider(KEY,'claude-sonnet-4-6').check()

    @patch('hyperpass.model_providers.urllib.request.build_opener')
    def test_authentication_is_header_only_and_redirects_disabled(self,build):
        build.return_value.open.return_value.__enter__.return_value.read.return_value=b'{}'
        for provider,url,header in [('anthropic','https://api.anthropic.com/v1/models','X-api-key'),
                                    ('gemini','https://generativelanguage.googleapis.com/v1beta/models','X-goog-api-key'),
                                    ('openai','https://api.openai.com/v1/models','Authorization')]:
            _request(provider,'GET',url,KEY)
            req=build.return_value.open.call_args.args[0]
            self.assertIn(KEY,req.get_header(header))
            self.assertNotIn(KEY,req.full_url)
            self.assertIsInstance(build.call_args.args[0],_NoRedirect)

    @patch('hyperpass.model_providers.urllib.request.build_opener')
    def test_provider_errors_redact_body_url_and_key(self,build):
        for code in (302,400,401,403,404,429,500):
            stream=io.BytesIO((KEY+' server-secret').encode())
            build.return_value.open.side_effect=urllib.error.HTTPError('https://secret.example/'+KEY,code,KEY,{},stream)
            with self.subTest(status=code),self.assertRaises(ProviderError) as caught:
                _request('anthropic','GET','https://api.anthropic.com/v1/models',KEY)
            self.assertNotIn(KEY,str(caught.exception))
            self.assertNotIn('server-secret',str(caught.exception))
            self.assertTrue(stream.closed)

    @patch('hyperpass.model_providers.urllib.request.build_opener')
    def test_rejects_foreign_hosts_and_oversized_response(self,build):
        for url in ('http://api.anthropic.com/v1/models','https://api.anthropic.com.evil.test/v1/models','https://user@api.anthropic.com/v1/models'):
            with self.assertRaises(ProviderError): _request('anthropic','GET',url,KEY)
        build.assert_not_called()
        with patch('hyperpass.model_providers.MAX_RESPONSE',20):
            build.return_value.open.return_value.__enter__.return_value.read.return_value=b' '*21
            with self.assertRaisesRegex(ProviderError,'너무 큽니다'):
                _request('anthropic','GET','https://api.anthropic.com/v1/models',KEY)


class ModelSelectionTests(unittest.TestCase):
    def test_model_names_do_not_allow_path_or_query_injection(self):
        for model in ('../x','x?key=abc','x/y','x\r\nHeader: bad',''):
            with self.subTest(model=model),self.assertRaises(ProviderError): validate_model_name('gemini',model)
        with self.assertRaises(ProviderError): validate_model_name([], 'model')

    def test_reasoning_choices_are_model_specific_not_codex_labels(self):
        ids=lambda vendor,model:[r['id'] for r in reasoning_options(vendor,model)]
        self.assertEqual(ids('openai','gpt-5-mini'),['default','minimal','low','medium','high'])
        self.assertEqual(ids('openai','gpt-5-mini-2025-08-07'),ids('openai','gpt-5-mini'))
        self.assertEqual(ids('openai','gpt-5-mini-2027-01-01'),['default'])
        self.assertEqual(ids('openai','gpt-6.2-astra'),['default','low','medium','high','xhigh','max'])
        self.assertEqual(ids('openai','gpt-5.2'),['default','none','low','medium','high','xhigh'])
        self.assertNotIn('xhigh',ids('anthropic','claude-opus-4-6'))
        self.assertIn('xhigh',ids('anthropic','claude-opus-4-7'))
        self.assertEqual(ids('anthropic','claude-opus-4-5'),['default'])
        self.assertEqual(ids('anthropic','claude-sonnet-4-6-20261225'),['default'])
        self.assertEqual(ids('gemini','gemini-3-pro-preview'),['default','low','high'])
        self.assertEqual(ids('gemini','gemini-2.5-pro'),['default','budget_1024','budget_4096','budget_8192'])
        self.assertEqual(ids('gemini','unknown-new-model'),['default'])
        self.assertEqual(ids('openai','gpt-5-pro'),['default'])

    @patch('hyperpass.model_providers._request')
    def test_unsupported_effort_rejected_before_network(self,request):
        for vendor,model,level in [('openai','gpt-6.2-astra','ultra'),('openai','gpt-5-mini','max'),
                                   ('anthropic','claude-sonnet-4-6','xhigh'),('gemini','gemini-3-pro-preview','medium'),
                                   ('gemini','unverified-model','high')]:
            with self.subTest(vendor=vendor,model=model),self.assertRaises(ProviderError):
                make_provider(vendor,KEY,model,reasoning=level)
        request.assert_not_called()

    @patch('hyperpass.provider._open')
    def test_openai_effort_sent_exactly_and_default_omitted(self,opener):
        opener.return_value.__enter__.return_value.read.return_value=json.dumps({'id':'r','status':'completed',
            'output':[{'type':'message','content':[{'type':'output_text','text':'{"ok":true}'}]}]}).encode()
        make_provider('openai',KEY,'gpt-6.2-astra','max').complete('',{},schema=CHECK_SCHEMA)
        self.assertEqual(json.loads(opener.call_args.args[0].data)['reasoning'],{'effort':'max'})
        make_provider('openai',KEY,'gpt-5-mini').complete('',{},schema=CHECK_SCHEMA)
        self.assertNotIn('reasoning',json.loads(opener.call_args.args[0].data))

    @patch('hyperpass.model_providers._request')
    def test_model_discovery_uses_actual_list_and_pages(self,request):
        request.side_effect=[{'data':[{'id':'claude-sonnet-4-6','display_name':'Sonnet'}],'has_more':True,'last_id':'model-a'},
                             {'data':[{'id':'claude-opus-4-6'}],'has_more':False}]
        rows=list_models('anthropic',KEY)
        self.assertEqual([r['id'] for r in rows],['claude-sonnet-4-6','claude-opus-4-6'])
        self.assertIn('after_id=model-a',request.call_args.args[2])
        self.assertIn('reasoning_options',rows[0])
        self.assertNotIn(KEY,json.dumps(rows))

    @patch('hyperpass.model_providers._request')
    def test_discovery_filters_models_without_text_generation(self,request):
        request.return_value={'models':[{'name':'models/gemini-3-flash-preview','supportedGenerationMethods':['generateContent']},
                                       {'name':'models/text-embedding-004','supportedGenerationMethods':['embedContent']}]}
        self.assertEqual([r['id'] for r in list_models('gemini',KEY)],['gemini-3-flash-preview'])
        request.return_value={'data':[{'id':'gpt-5-mini'},{'id':'gpt-audio'},{'id':'text-embedding-3-small'}]}
        self.assertEqual([r['id'] for r in list_models('openai',KEY)],['gpt-5-mini'])

    @patch('hyperpass.model_providers.make_provider')
    def test_role_assignment_falls_back_only_to_explicit_run_default(self,factory):
        factory.side_effect=lambda *a,**k: Mock(complete=Mock(return_value={'data':{'ok':True}}))
        mapping={'default':{'provider':'openai','model':'gpt-5-mini','reasoning':'low'},
                 'roles':{'risk-manager':{'provider':'anthropic','model':'claude-sonnet-4-6','reasoning':'high'}}}
        provider=RoutedProvider(mapping,{'openai':KEY,'anthropic':{'api_key':KEY}})
        head=provider.complete('',{'stage':'plan'})
        specialist=provider.complete('',{'role':'risk-manager'})
        self.assertEqual(head['provider'],'openai')
        self.assertEqual(head['reasoning'],'low')
        self.assertEqual(specialist['provider'],'anthropic')
        self.assertEqual(specialist['reasoning'],'high')
        self.assertEqual(factory.call_count,2)
        mapping['default']['model']='mutated'
        self.assertEqual(provider.describe('head-manager')['model'],'gpt-5-mini')

    def test_missing_keys_and_unknown_config_fields_fail_early(self):
        with self.assertRaisesRegex(ProviderError,'API 키를 먼저'):
            RoutedProvider({'default':{'provider':'gemini','model':'gemini-3-flash-preview'}},{})
        for config in ({'default':{'provider':'openai','model':'gpt-5-mini','api_key':KEY}},
                       {'default':{'provider':'openai','model':'gpt-5-mini'},'unexpected':KEY},
                       {'default':{'provider':'openai','model':'gpt-5-mini'},'roles':{'invented-role':{}}}):
            with self.assertRaises(ProviderError): RoutedProvider(config,{'openai':KEY})


if __name__=='__main__': unittest.main()
