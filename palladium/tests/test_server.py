from datetime import datetime
import io
import json
import math
from threading import Thread
from unittest.mock import Mock
from unittest.mock import patch

import dateutil.parser
from flask import request
import numpy as np
import pytest
import ujson
from werkzeug.exceptions import BadRequest


class TestPredictService:
    @pytest.fixture
    def PredictService(self):
        from palladium.server import PredictService
        return PredictService

    def test_functional(self, PredictService, flask_app):
        model = Mock()
        model.threshold = 0.3
        model.size = 10
        # needed as hasattr would evaluate to True otherwise
        del model.threshold2
        del model.size2
        model.predict.return_value = np.array(['class1'])
        service = PredictService(
            mapping=[
                ('sepal length', 'float'),
                ('sepal width', 'float'),
                ('petal length', 'float'),
                ('petal width', 'float'),
                ('color', 'str'),
                ('age', 'int'),
                ('active', 'bool'),
                ('austrian', 'bool'),
                ],
            params=[
                ('threshold', 'float'),  # default will be overwritten
                ('size', 'int'),  # not provided, default value kept
                ('threshold2', 'float'),  # will be used, no default value
                ('size2', 'int'),  # not provided, no default value
                ])

        with flask_app.test_request_context():
            with patch('palladium.util.get_config') as get_config:
                get_config.return_value = {
                    'service_metadata': {
                        'service_name': 'iris',
                        'service_version': '0.1'
                    }
                }
                request = Mock(
                    args=dict([
                        ('sepal length', '5.2'),
                        ('sepal width', '3.5'),
                        ('petal length', '1.5'),
                        ('petal width', '0.2'),
                        ('color', 'purple'),
                        ('age', '1'),
                        ('active', 'True'),
                        ('austrian', 'False'),
                        ('threshold', '0.7'),
                        ('threshold2', '0.8'),
                        ]),
                    method='GET',
                    )
                resp = service(model, request)

        assert (model.predict.call_args[0][0] ==
                np.array([[5.2, 3.5, 1.5, 0.2,
                           'purple', 1, True, False]], dtype='object')).all()
        assert model.predict.call_args[1]['threshold'] == 0.7
        assert model.predict.call_args[1]['size'] == 10
        assert model.predict.call_args[1]['threshold2'] == 0.8
        assert 'size2' not in model.predict.call_args[1]
        assert resp.status_code == 200
        expected_resp_data = {
            "metadata": {
                "status": "OK",
                "error_code": 0,
                "service_name": "iris",
                "service_version": "0.1",
                },
            "result": "class1"
            }

        assert json.loads(resp.get_data(as_text=True)) == expected_resp_data

    def test_bad_request(self, PredictService, flask_app):
        predict_service = PredictService(mapping=[])
        model = Mock()
        request = Mock()
        with patch.object(predict_service, 'do') as psd:
            with flask_app.test_request_context():
                bad_request = BadRequest()
                bad_request.args = ('daniel',)
                psd.side_effect = bad_request
                resp = predict_service(model, request)
        resp_data = json.loads(resp.get_data(as_text=True))
        assert resp.status_code == 400
        assert resp_data == {
            "metadata": {
                "status": "ERROR",
                "error_code": -1,
                "error_message": "BadRequest: ('daniel',)"
                }
            }

    def test_predict_error(self, PredictService, flask_app):
        from palladium.interfaces import PredictError
        predict_service = PredictService(mapping=[])
        model = Mock()
        request = Mock()
        with patch.object(predict_service, 'do') as psd:
            with flask_app.test_request_context():
                psd.side_effect = PredictError("mymessage", 123)
                resp = predict_service(model, request)
        resp_data = json.loads(resp.get_data(as_text=True))
        assert resp.status_code == 500
        assert resp_data == {
            "metadata": {
                "status": "ERROR",
                "error_code": 123,
                "error_message": "mymessage",
                }
            }

    def test_generic_error(self, PredictService, flask_app):
        predict_service = PredictService(mapping=[])
        model = Mock()
        request = Mock()
        with patch.object(predict_service, 'do') as psd:
            with flask_app.test_request_context():
                psd.side_effect = KeyError("model")
                resp = predict_service(model, request)
        resp_data = json.loads(resp.get_data(as_text=True))
        assert resp.status_code == 500
        assert resp_data == {
            "metadata": {
                "status": "ERROR",
                "error_code": -1,
                "error_message": "KeyError: 'model'",
                }
            }

    def test_sample_from_data(self, PredictService):
        predict_service = PredictService(
            mapping=[
                ('name', 'str'),
                ('sepal width', 'int'),
                ],
            )

        model = Mock()
        request_args = {'name': 'myflower', 'sepal width': 3}
        sample = predict_service.sample_from_data(model, request_args)
        assert sample[0] == 'myflower'
        assert sample[1] == 3

    def test_probas(self, PredictService, flask_app):
        model = Mock()
        model.predict_proba.return_value = np.array([[0.1, 0.5, math.pi]])
        predict_service = PredictService(mapping=[], predict_proba=True)
        with flask_app.test_request_context():
            resp = predict_service(model, request)
        resp_data = json.loads(resp.get_data(as_text=True))
        assert resp.status_code == 200
        assert resp_data == {
            "metadata": {
                "status": "OK",
                "error_code": 0,
                },
            "result": [0.1, 0.5, math.pi],
            }

    def test_post_request(self, PredictService, flask_app):
        model = Mock()
        model.predict.return_value = np.array([3, 2])

        service = PredictService(
            mapping=[
                ('sepal length', 'float'),
                ('sepal width', 'float'),
                ('petal length', 'float'),
                ('petal width', 'float'),
                ],
            params=[
                ('threshold', 'float'),
                ],
            )

        request = Mock(
            json=[
                {
                    'sepal length': '5.2',
                    'sepal width': '3.5',
                    'petal length': '1.5',
                    'petal width': '0.2',
                    },
                {
                    'sepal length': '5.7',
                    'sepal width': '4.0',
                    'petal length': '2.0',
                    'petal width': '0.7',
                    },
                ],
            args=dict(threshold=1.0),
            method='POST',
            mimetype='application/json',
            )

        with flask_app.test_request_context():
            resp = service(model, request)

        assert (model.predict.call_args[0][0] == np.array([
            [5.2, 3.5, 1.5, 0.2],
            [5.7, 4.0, 2.0, 0.7],
            ],
            dtype='object',
            )).all()
        assert model.predict.call_args[1]['threshold'] == 1.0

        assert resp.status_code == 200
        expected_resp_data = {
            "metadata": {
                "status": "OK",
                "error_code": 0,
                },
            "result": [3, 2],
            }

        assert json.loads(resp.get_data(as_text=True)) == expected_resp_data


class TestPredict:
    @pytest.fixture
    def predict(self):
        from palladium.server import predict
        return predict

    def test_predict_functional(self, config, flask_app, flask_client):
        from palladium.server import make_ujson_response
        model_persister = config['model_persister'] = Mock()
        predict_service = config['predict_service'] = Mock()
        with flask_app.test_request_context():
            predict_service.return_value = make_ujson_response(
                'a', status_code=200)

        model = model_persister.read()

        resp = flask_client.get(
            'predict?sepal length=1.0&sepal width=1.1&'
            'petal length=0.777&petal width=5')

        resp_data = json.loads(resp.get_data(as_text=True))

        assert resp_data == 'a'
        assert resp.status_code == 200
        with flask_app.test_request_context():
            predict_service.assert_called_with(model, request)

    def test_unknown_exception(self, predict, flask_app):
        model_persister = Mock()
        model_persister.read.side_effect = KeyError('model')

        with flask_app.test_request_context():
            resp = predict(model_persister, Mock())
        resp_data = json.loads(resp.get_data(as_text=True))
        assert resp.status_code == 500
        assert resp_data == {
            "status": "ERROR",
            "error_code": -1,
            "error_message": "KeyError: 'model'",
            }


class TestAliveFunctional:
    def test_empty_process_state(self, config, flask_client):
        config['service_metadata'] = {'hello': 'world'}
        resp = flask_client.get('alive')
        assert resp.status_code == 200
        resp_data = json.loads(resp.get_data(as_text=True))

        assert sorted(resp_data.keys()) == ['memory_usage',
                                            'memory_usage_vms',
                                            'palladium_version',
                                            'service_metadata']
        assert resp_data['service_metadata'] == config['service_metadata']

    def test_filled_process_state(self, config, process_store, flask_client):
        config['alive'] = {'process_store_required': ('model', 'data')}

        before = datetime.now()
        process_store['model'] = Mock(__metadata__={'hello': 'is it me'})
        process_store['data'] = Mock(__metadata__={'bye': 'not you'})
        after = datetime.now()

        resp = flask_client.get('alive')
        assert resp.status_code == 200
        resp_data = json.loads(resp.get_data(as_text=True))

        model_updated = dateutil.parser.parse(resp_data['model']['updated'])
        data_updated = dateutil.parser.parse(resp_data['data']['updated'])
        assert before < model_updated < after
        assert resp_data['model']['metadata'] == {'hello': 'is it me'}
        assert before < data_updated < after
        assert resp_data['data']['metadata'] == {'bye': 'not you'}

    def test_missing_process_state(self, config, process_store, flask_client):
        config['alive'] = {'process_store_required': ('model', 'data')}
        process_store['model'] = Mock(__metadata__={'hello': 'is it me'})

        resp = flask_client.get('alive')
        assert resp.status_code == 503
        resp_data = json.loads(resp.get_data(as_text=True))

        assert resp_data['model']['metadata'] == {'hello': 'is it me'}
        assert resp_data['data'] == 'N/A'


class TestPredictStream:
    @pytest.fixture
    def PredictStream(self):
        from palladium.server import PredictStream
        return PredictStream

    @pytest.fixture
    def stream(self, config, PredictStream):
        config['model_persister'] = Mock()
        predict_service = config['predict_service'] = Mock()
        predict_service.sample_from_data.side_effect = (
            lambda model, data: data)
        predict_service.params_from_data.side_effect = (
            lambda model, data: data)
        return PredictStream()

    def test_listen_direct_exit(self, stream):
        io_in = io.StringIO()
        io_out = io.StringIO()
        io_err = io.StringIO()
 
        stream_thread = Thread(
            target=stream.listen(io_in, io_out, io_err))
        stream_thread.start()
        io_in.write('EXIT\n')
        stream_thread.join()
        io_out.seek(0)
        io_err.seek(0)
        assert len(io_out.read()) == 0
        assert len(io_err.read()) == 0
        assert stream.predict_service.predict.call_count == 0

    def test_listen(self, stream):
        io_in = io.StringIO()
        io_out = io.StringIO()
        io_err = io.StringIO()
        lines = [
            '[{"id": 1, "color": "blue", "length": 1.0}]\n',
            '[{"id": 1, "color": "{\\"a\\": 1, \\"b\\": 2}", "length": 1.0}]\n',
            '[{"id": 1, "color": "blue", "length": 1.0}, {"id": 2, "color": "{\\"a\\": 1, \\"b\\": 2}", "length": 1.0}]\n',
        ]
        for line in lines:
            io_in.write(line)
 
        io_in.write('EXIT\n')
        io_in.seek(0)
        predict = stream.predict_service.predict
        predict.side_effect = (
            lambda model, samples, **params:
            np.array([{'result': 1}] * len(samples))
            )
        stream_thread = Thread(
            target=stream.listen(io_in, io_out, io_err))
        stream_thread.start()
        stream_thread.join()
        io_out.seek(0)
        io_err.seek(0)
        assert len(io_err.read()) == 0
        assert io_out.read() == (
            ('[{"result":1}]\n' * 2) + ('[{"result":1},{"result":1}]\n'))
        assert predict.call_count == 3
        # check if the correct arguments are passed to predict call
        assert predict.call_args_list[0][0][1] == np.array([
            {'id': 1, 'color': 'blue', 'length': 1.0}])
        assert predict.call_args_list[1][0][1] == np.array([
            {'id': 1, 'color': '{"a": 1, "b": 2}', 'length': 1.0}])
        assert (predict.call_args_list[2][0][1] == np.array([
            {'id': 1, 'color': 'blue', 'length': 1.0},
            {'id': 2, 'color': '{"a": 1, "b": 2}', 'length': 1.0},
            ])).all()

        # check if string representation of attribute can be converted to json
        assert ujson.loads(predict.call_args_list[1][0][1][0]['color']) == {
            "a": 1, "b": 2}
 
    def test_predict_error(self, stream):
        from palladium.interfaces import PredictError

        io_in = io.StringIO()
        io_out = io.StringIO()
        io_err = io.StringIO()
 
        line = '[{"hey": "1"}]\n'
        io_in.write(line)
        io_in.write('EXIT\n')
        io_in.seek(0)
        stream.predict_service.predict.side_effect = PredictError('error')

        stream_thread = Thread(
            target=stream.listen(io_in, io_out, io_err))
        stream_thread.start()
        stream_thread.join()

        io_out.seek(0)
        io_err.seek(0)
        assert io_out.read() == '[]\n'
        assert io_err.read() == (
            "Error while processing input row: {}"
            "<class 'palladium.interfaces.PredictError'>: "
            "error (-1)\n".format(line))
        assert stream.predict_service.predict.call_count == 1

    def test_predict_params(self, config, stream):
        from palladium.server import PredictService
        line = '[{"length": 1.0, "width": 1.0, "turbo": "true"}]'

        model = Mock()
        model.predict.return_value = np.array([[{'class': 'a'}]])
        model.turbo = False
        model.magic = False
        stream.model = model

        mapping = [
            ('length', 'float'),
            ('width', 'float'),
            ]
        params = [
            ('turbo', 'bool'),  # will be set by request args
            ('magic', 'bool'),  # default value will be used
            ]
        stream.predict_service = PredictService(
            mapping=mapping,
            params=params,
        )

        expected = [{'class': 'a'}]
        result = stream.process_line(line)
        assert result == expected
        assert model.predict.call_count == 1
        assert (model.predict.call_args[0][0] == np.array([[1.0, 1.0]])).all()
        assert model.predict.call_args[1]['turbo'] is True
        assert model.predict.call_args[1]['magic'] is False
