import argparse
import binascii
import json
import communityid

from rich.console import Console

console = Console()


def _clean_ip_address(ip):
    if ip.startswith('::ffff:') and ip.count('.') == 3:
        return ip.replace('::ffff:', '')
    return ip

def compute_community_id(trace):
    cid = communityid.CommunityID()
    src_ip = _clean_ip_address(trace['data']['local_ip'])
    src_port = trace['data']['local_port']
    dst_ip = _clean_ip_address(trace['data']['dest_ip'])
    dst_port = trace['data']['dest_port']
    
    if 'tcp' in trace['data']['socket_type']:
        tpl = communityid.FlowTuple.make_tcp(src_ip, dst_ip, src_port, dst_port)
    else:
        tpl = communityid.FlowTuple.make_udp(src_ip, dst_ip, src_port, dst_port)

    return {
        'src_ip': src_ip,
        'src_port': src_port,
        'dst_ip': dst_ip,
        'dst_port': dst_port,
        'community_id': cid.calc(tpl)
    }


def build_community_id_stack_traces(socket_trace_file):
    socket_traces = json.load(socket_trace_file) 
    stack_traces = {}

    for trace in socket_traces:
        flow_data = compute_community_id(trace)
        trace['data']['local_ip'] = flow_data.get('src_ip')
        trace['data']['dest_ip'] = flow_data.get('dst_ip')
        trace['data']['community_id'] = flow_data.get('community_id')
        if not flow_data.get('community_id') in stack_traces:
            stack_traces[flow_data.get('community_id')] = trace

    return stack_traces


def _compact_stack_trace(trace):
    clean_stack = []
    stack = trace['data']['stack']
    for call in stack:
        clazz = call.get('class')
        if clazz not in clean_stack:
            clean_stack.append(clazz)
    return clean_stack


def parse_ip_layer(ip_layer: dict):
    try:
        return {
                   'ip': ip_layer.get('ip_ip_src'),
                   'host': ip_layer.get('ip_ip_src_host')
               }, {
                   'ip': ip_layer.get('ip_ip_dst'),
                   'host': ip_layer.get('ip_ip_dst_host'),
               }
    except Exception as e:
        return None


def parse_eth_layer(eth_layer: dict):
    return {
               'mac': eth_layer.get('eth_eth_src')
           }, {
               'mac': eth_layer.get('eth_eth_dst'),
           }


def parse_sll_layer(sll_layer: dict):
    return {
               'mac': sll_layer.get('sll_sll_src_eth')
           }, {
               'mac': None,
           }


def parse_single_http2_layer(http2_layer: dict):
    data, headers = None, None
    if 'http2_http2_body_reassembled_data' in http2_layer:
        raw_data = http2_layer.get('http2_http2_body_reassembled_data', '')
        if type(raw_data) is list:
            raw_data = ':'.join(http2_layer.get('http2_http2_body_reassembled_data', ''))
        raw_data = raw_data.replace(':', '')
        data = binascii.unhexlify(raw_data)
        try:
            data = data.decode('utf-8')
        except Exception:
            data = raw_data
    elif 'http2_http2_data_data' in http2_layer:
        raw_data = http2_layer.get('http2_http2_data_data', '')
        if type(raw_data) is list:
            raw_data = ':'.join(http2_layer.get('http2_http2_data_data', ''))
        raw_data = raw_data.replace(':', '')
        data = binascii.unhexlify(raw_data)
        try:
            data = data.decode('utf-8')
        except Exception:
            data = raw_data
    if 'http2_http2_headers' in http2_layer:
        header_name = http2_layer.get('http2_http2_header_name')
        header_value = http2_layer.get('http2_http2_header_value')
        if len(header_name) != len(header_value):
            print('ERROR http2 unmatched header names with values')
            return headers, data
        headers = dict([x for x in zip(header_name, header_value)])
    return headers, data


def parse_http2(layers: dict, layer_names: list):
    to_return = []
    http2_layer = layers.get('http2')
    if type(http2_layer) is list:
        for l in http2_layer:
            headers, data = parse_single_http2_layer(l)
            to_return.append({
                'headers': headers,
                'data': data
            })
    else:
        headers, data = parse_single_http2_layer(http2_layer)
        to_return.append({
            'headers': headers,
            'data': data
        })
    return to_return


def parse_http3(layers: dict, layer_names: list):
    headers, data = None, None
    http3_layer = layers.get('http3')
    # if type(http_layer) is list:
    #    for l in http_layer:
    #        parse_single_http_layer(l)
    # else:
    #    parse_single_http2_layer(http2_layer)
    return headers, data


def parse_http(layers: dict, layer_names: list):
    headers, data = None, None
    http_layer = layers.get('http')
    if http_layer and type(http_layer) is list: # list in case of websocket communication
        http_layer = http_layer[0]
    data = http_layer.get('http_http_file_data', '')
    raw_headers = None
    if 'http_http_response_line' in http_layer:
        raw_headers = http_layer.get('http_http_response_line')
    if 'http_http_request_line' in http_layer:
        raw_headers = http_layer.get('http_http_request_line')
    headers = {}
    for line in raw_headers:
        i = line.find(': ')
        name = line[:i].strip()
        value = line[i + 1:].strip()
        headers[name] = value
    if 'http_http_response_for_uri' in http_layer:
        headers['uri'] = http_layer.get('http_http_response_for_uri')
    elif 'http_http_request_full_uri' in http_layer:
        headers['uri'] = http_layer.get('http_http_request_full_uri')
    headers['is_request'] = 'http_http_request' in http_layer
    return [{'headers': headers, 'data': data}]

    # 'http_http_request_line' // request headers
    # 'http_http_request_method'
    # 'http_http_request_full_uri'
    # 'http_http_file_data' // data if sent

    # 'http_http_response_code' (+ 'http_http_response_code_desc' pour lisibilité)
    # 'http_http_response_line' // response headers
    # 'http_http_response_for_uri' // uri which replies
    # 'http_http_file_data'

    # if type(http_layer) is list:
    #    for l in http_layer:
    #        parse_single_http_layer(l)
    # else:
    #    parse_single_http2_layer(http2_layer)


def get_top_most_layers(packet, protocol, protocol_stack):
    i = protocol_stack.find(f':{protocol}')
    top_most_layer_names = protocol_stack[i + 1:].split(':')
    top_most_layers = {k: packet.get('layers').get(k) for k in top_most_layer_names}
    return top_most_layers, top_most_layer_names


def dispatch(packet):
    protocol_stack = packet.get('layers').get('frame').get('frame_frame_protocols')
    packets = []
    packet_description = {
        'src': {},
        'dst': {},
        'timestamp': packet.get('timestamp'),
        'community_id': packet.get('layers').get('communityid_communityid'),
        'headers': None,
        'data': None,
        'protocol_stack': protocol_stack
    }
    if 'ip' not in packet.get('layers'):
        return None

    src_ip, dst_ip = parse_ip_layer(packet.get('layers').get('ip'))
    if protocol_stack.startswith('eth:'):
        src_eth, dst_eth = parse_eth_layer(packet.get('layers').get('eth'))
    if protocol_stack.startswith('sll:'):
        src_eth, dst_eth = parse_sll_layer(packet.get('layers').get('sll'))
    packet_description['src'].update(src_ip)
    packet_description['src'].update(src_eth)
    packet_description['dst'].update(dst_ip)
    packet_description['dst'].update(dst_eth)

    if ':http3' in protocol_stack:
        top_most_layers, top_most_layer_names = get_top_most_layers(packet, 'http3', protocol_stack)
        parse_http3(top_most_layers, top_most_layer_names)
        return
    elif ':http2' in protocol_stack:
        top_most_layers, top_most_layer_names = get_top_most_layers(packet, 'http2', protocol_stack)
        ret = parse_http2(top_most_layers, top_most_layer_names)
        for r in ret:
            pd = packet_description.copy()
            if r['headers'] or r['data']:
                pd['headers'] = r['headers']
                pd['data'] = r['data']
                packets.append(pd)
        return packets
    elif ':http' in protocol_stack:
        top_most_layers, top_most_layer_names = get_top_most_layers(packet, 'http', protocol_stack)
        ret = parse_http(top_most_layers, top_most_layer_names)
        for r in ret:
            pd = packet_description.copy()
            if r['headers'] or r['data']:
                pd['headers'] = r['headers']
                pd['data'] = r['data']
                packets.append(pd)
        return packets


def view_decrypted_traffic():
    arg_parser = argparse.ArgumentParser(prog='pirogue', description='View decrypted TLS traffic')
    arg_parser.add_argument('-i', '--input', dest='infile', type=argparse.FileType('r'), required=True,
                        metavar='INPUT_FILE', help='The JSON file generated by tshark -2 -T ek --enable-protocol communityid -Ndmn <pcapng file> > <output json file>')
    arg_parser.add_argument('-t', '--traces', dest='socket_traces', type=argparse.FileType('r'), required=False,
                        metavar='INPUT_FILE', help='The JSON file containing stack traces of socket operations')
    args = arg_parser.parse_args()
    traffic_json_file = args.infile

    socket_traces_file = args.socket_traces
    socket_traces = None
    if socket_traces_file:
        socket_traces = build_community_id_stack_traces(socket_traces_file)

    if not traffic_json_file.name.endswith('.json'):
        console.log('Wrong format of input file. JSON is expected')
        return

    for line in traffic_json_file.readlines():
        if line.startswith('{"timestamp":'):
            packet = json.loads(line)
            d = dispatch(packet)
            if not d:
                continue
            for p in d:
                try:
                    if p.get('data'):
                        source = p.get('src').get('ip') + ' / ' + p.get('src').get('host')
                        destination = p.get('dst').get('ip') + ' / ' + p.get('dst').get('host')
                        console.rule(f"[purple] {source} -> {destination}", align='left')
                        console.print(f"[plum4]Community ID: {p.get('community_id')}")
                        if socket_traces and p.get('community_id') in socket_traces:
                            console.print(f"[plum4]Stack trace:")
                            console.print(_compact_stack_trace(socket_traces.get(p.get('community_id'))))
                        console.print(f"[plum4]Headers:")
                        console.print(p.get('headers'))
                        console.print(f"[plum4]Data:")
                        try:
                            json_data = json.loads(p.get('data'))
                            console.print(json.dumps(json_data, indent=2))
                        except Exception:
                            console.print(p.get('data'))
                        console.print()
                except:
                    pass
